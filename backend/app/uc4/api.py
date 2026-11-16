"""UC4 HTTP API: cases, diagnosis (via the team's pipeline), saved diagnoses and reviewer feedback.

Every response uses one envelope:
    success: {"ok": true,  "data": ...,  "error": null}
    error:   {"ok": false, "data": null, "error": {"code": "...", "message": "..."}}

What this module does NOT do: it never diagnoses anything itself. POST /api/diagnose calls
app.uc4.pipeline.diagnose (owned by the pipeline team). Until that exists, the endpoint answers
503 DIAGNOSIS_NOT_READY; the rest of the API keeps working.

Reused modules (not modified): store.py (cases, logs), audit.py (SQLite audit log, masking before
storage), redact.py (masking reviewer notes), models.py (Case; Diagnosis when it exists).
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.uc4 import audit, store
from app.uc4.models import Case
from app.uc4.redact import mask_text
from app.uc4.settings import BACKEND_DIR

logger = logging.getLogger(__name__)

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"
MAX_NOTE_CHARS = audit.MAX_NOTE_CHARS
DIAGNOSIS_FIELDS = (
    "diagnosis_id", "created_at", "case_id", "route", "onset_ts", "outcome", "failure_class",
    "class_confidence", "causes", "evidence", "missing_info", "report", "report_findings",
    "generator", "trace",
)
OUTCOMES = ("RECOMMEND", "CLARIFY", "ESCALATE")
# Case fields that are evaluation answers or bookkeeping: never shown, never given to the pipeline.
LABEL_FIELDS = ("split", "difficulty", "expected_class", "expected_cause", "expected_first_check",
                "expected_outcome", "requires_escalation", "culprit_dependency", "culprit_client",
                "missing_info", "worked_example", "human_verify_suggested", "summary", "generation")


# ---------- settings ----------

@dataclass(frozen=True)
class ApiSettings:
    """Runtime settings, read from environment variables (see load_api_settings)."""

    audit_db_path: Path
    cors_origins: tuple[str, ...]
    diagnose_timeout_s: float


def load_api_settings() -> ApiSettings:
    """Read UC4_AUDIT_DB, UC4_CORS_ORIGINS and UC4_DIAGNOSE_TIMEOUT_S, with safe local defaults."""
    db = os.environ.get("UC4_AUDIT_DB", "").strip()
    db_path = Path(db) if db else BACKEND_DIR / "data" / "audit" / "uc4_audit.db"
    origins = os.environ.get("UC4_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    cors = tuple(o.strip() for o in origins.split(",") if o.strip())
    if "*" in cors:
        raise ValueError("UC4_CORS_ORIGINS must list exact origins, not '*'")
    raw_timeout = os.environ.get("UC4_DIAGNOSE_TIMEOUT_S", "60")
    try:
        timeout = float(raw_timeout)
    except ValueError:
        raise ValueError("UC4_DIAGNOSE_TIMEOUT_S must be a number of seconds") from None
    if not 0 < timeout <= 600:
        raise ValueError("UC4_DIAGNOSE_TIMEOUT_S must be between 0 and 600 seconds")
    return ApiSettings(audit_db_path=db_path, cors_origins=cors, diagnose_timeout_s=timeout)


# ---------- envelope and errors ----------

class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    ok: Literal[False] = False
    data: None = None
    error: ErrorBody


class ApiError(Exception):
    """An expected failure, turned into the error envelope by the handler in main.py."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def ok(data: Any, status: int = 200) -> JSONResponse:
    """The success envelope."""
    return JSONResponse(status_code=status, content={"ok": True, "data": data, "error": None})


def error_response(status: int, code: str, message: str) -> JSONResponse:
    """The error envelope (used by every exception handler)."""
    return JSONResponse(status_code=status,
                        content={"ok": False, "data": None, "error": {"code": code, "message": message}})


def _error_docs(*items: tuple[int, str]) -> dict[int, dict[str, Any]]:
    return {status: {"model": ErrorEnvelope, "description": text} for status, text in items}


# ---------- request / response models ----------

class CaseSummary(BaseModel):
    """What the case picker shows. No labels, no raw log data."""

    model_config = ConfigDict(extra="forbid")
    id: str
    route: str
    summary: str
    split: str


class CaseListEnvelope(BaseModel):
    ok: Literal[True] = True
    data: list[CaseSummary]
    error: None = None


class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=ID_PATTERN, description="Case to diagnose, e.g. UC4-0050")


class FeedbackRequest(BaseModel):
    """A reviewer verdict. 'annotate' needs a note; cause_id must name a cause of the diagnosis."""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["confirm", "reject", "annotate"]
    cause_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    note: Optional[str] = Field(default=None, max_length=MAX_NOTE_CHARS)

    @model_validator(mode="after")
    def _annotate_needs_note(self) -> "FeedbackRequest":
        if self.note is not None and not self.note.strip():
            self.note = None
        if self.verdict == "annotate" and self.note is None:
            raise ValueError("an annotate verdict needs a note")
        return self


class DiagnosisEnvelope(BaseModel):
    ok: Literal[True] = True
    data: dict[str, Any] = Field(description="The full Diagnosis (schema owned by the pipeline), secrets masked")
    error: None = None


class FeedbackRecord(BaseModel):
    feedback_id: str
    diagnosis_id: str
    case_id: str
    verdict: str
    cause_id: Optional[str]
    note: Optional[str]
    created_at: str
    request_id: Optional[str]


class FeedbackEnvelope(BaseModel):
    ok: Literal[True] = True
    data: FeedbackRecord
    error: None = None


class FeedbackListEnvelope(BaseModel):
    ok: Literal[True] = True
    data: list[FeedbackRecord]
    error: None = None


class ChainEnvelope(BaseModel):
    ok: Literal[True] = True
    data: dict[str, Any]
    error: None = None


# ---------- dependencies (overridable in tests) ----------

@dataclass
class CaseSource:
    """Where cases come from. Default: store.py (cached after the first call)."""

    load_cases: Callable[[], dict[str, Case]] = store.load_cases
    focal_status: Callable[[str], Optional[int]] = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.focal_status is None:
            self.focal_status = _focal_status_from_logs


def _focal_status_from_logs(correlation_id: str) -> Optional[int]:
    rows = store.logs_by_correlation_id(correlation_id)
    status = rows[0].get("status") if rows else None
    return status if isinstance(status, int) else None


def get_case_source() -> CaseSource:
    """Dependency: the case source."""
    return CaseSource()


def get_settings(request: Request) -> ApiSettings:
    """Dependency: settings stored on the app at startup."""
    return request.app.state.settings


def get_request_id(request: Request) -> Optional[str]:
    """Dependency: the validated request id set by the middleware."""
    return getattr(request.state, "request_id", None)


PipelineFn = Callable[[Case], Any]


def resolve_pipeline() -> tuple[Optional[PipelineFn], str]:
    """Find app.uc4.pipeline.diagnose. Returns (callable taking a Case, status text).

    Accepted signatures: diagnose(case) or diagnose(case_id) with one required parameter.
    Anything else is reported as not ready rather than guessed at.
    """
    try:
        module = importlib.import_module("app.uc4.pipeline")
    except ModuleNotFoundError as exc:
        if exc.name in ("app.uc4.pipeline",):
            return None, "pipeline module not available yet"
        return None, f"pipeline cannot be imported (missing module {exc.name})"
    except Exception as exc:  # the pipeline's own import failed; report, don't crash the API
        return None, f"pipeline cannot be imported ({exc.__class__.__name__})"
    fn = getattr(module, "diagnose", None)
    if not callable(fn):
        return None, "pipeline has no diagnose() function"
    try:
        params = [p for p in inspect.signature(fn).parameters.values()
                  if p.default is inspect.Parameter.empty
                  and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    except (TypeError, ValueError):
        return None, "diagnose() signature cannot be inspected"
    if len(params) == 1 and params[0].name == "case":
        return (lambda case: fn(**{"case": case})), "ready"
    if len(params) == 1 and params[0].name == "case_id":
        return (lambda case: fn(**{"case_id": case.case_id})), "ready"
    return None, "diagnose() signature is not the agreed diagnose(case) or diagnose(case_id)"


def get_pipeline() -> Optional[PipelineFn]:
    """Dependency: the diagnosis callable, or None when the pipeline is not ready."""
    fn, status = resolve_pipeline()
    if fn is None:
        logger.debug("diagnosis pipeline not ready: %s", status)
    return fn


def _diagnosis_model() -> Optional[type[BaseModel]]:
    """The pipeline team's Diagnosis model from models.py, if it exists yet."""
    module = importlib.import_module("app.uc4.models")
    model = getattr(module, "Diagnosis", None)
    return model if isinstance(model, type) and issubclass(model, BaseModel) else None


# ---------- helpers ----------

def build_case_summary(case: Case, focal_status: Optional[int]) -> CaseSummary:
    """A neutral one-line summary from observable facts only (never the dataset's labelled summary)."""
    when = case.onset_ts.strftime("%Y-%m-%d %H:%M UTC")
    status = f"HTTP {focal_status}" if focal_status is not None else "Failure"
    return CaseSummary(id=case.case_id, route=case.route, summary=f"{status} on {case.route}, onset {when}",
                       split=case.split or "unknown")


def strip_labels(case: Case) -> Case:
    """A copy of the case without labels, so the pipeline cannot read the answers."""
    return case.model_copy(update={name: Case.model_fields[name].get_default(call_default_factory=True)
                                   for name in LABEL_FIELDS})


def check_diagnosis(result: Any, case_id: str) -> dict[str, Any]:
    """Turn the pipeline's result into a dict and check the agreed contract; raise ApiError if broken."""
    model = _diagnosis_model()
    try:
        if model is not None:
            result = model.model_validate(result)
        if isinstance(result, BaseModel):
            result = result.model_dump(mode="json")
    except Exception as exc:
        logger.warning("pipeline returned an invalid Diagnosis (%s)", exc.__class__.__name__)
        raise ApiError(502, "DIAGNOSIS_INVALID", "The diagnosis service returned an invalid result.") from None
    if not isinstance(result, dict):
        raise ApiError(502, "DIAGNOSIS_INVALID", "The diagnosis service returned an invalid result.")

    problems = [f"missing field {name}" for name in DIAGNOSIS_FIELDS if name not in result]
    diagnosis_id = result.get("diagnosis_id")
    if not isinstance(diagnosis_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,199}", diagnosis_id):
        problems.append("diagnosis_id is missing or not a safe identifier")
    if result.get("case_id") != case_id:
        problems.append("case_id does not match the request")
    if result.get("outcome") not in OUTCOMES:
        problems.append("outcome is not RECOMMEND, CLARIFY or ESCALATE")
    if result.get("outcome") == "CLARIFY" and result.get("report") is not None:
        problems.append("report must be null when outcome is CLARIFY")
    for name in ("causes", "evidence", "missing_info", "report_findings", "trace"):
        if name in result and not isinstance(result[name], list):
            problems.append(f"{name} must be a list")
    if problems:
        logger.warning("pipeline Diagnosis breaks the contract: %s", "; ".join(problems))
        raise ApiError(502, "DIAGNOSIS_INVALID", "The diagnosis service returned an invalid result.")
    return result


def _cause_ids(diagnosis: dict[str, Any]) -> set[str]:
    causes = diagnosis.get("causes") or []
    return {c["cause_id"] for c in causes if isinstance(c, dict) and isinstance(c.get("cause_id"), str)}


def _storage_error(exc: Exception) -> ApiError:
    logger.error("audit database error (%s)", exc.__class__.__name__)
    return ApiError(503, "DATABASE_UNAVAILABLE", "The audit database is not available.")


# ---------- routes ----------

router = APIRouter(prefix="/api", tags=["uc4"])


@router.get(
    "/cases", response_model=CaseListEnvelope, summary="List cases",
    description="All failure cases for the case picker, sorted by id. Each item has id, route, a neutral "
                "summary (HTTP status, route, onset time) and split. Evaluation labels are never included.",
    responses=_error_docs((503, "CASES_UNAVAILABLE: case data could not be loaded")),
)
def list_cases(source: CaseSource = Depends(get_case_source)) -> JSONResponse:
    try:
        cases = source.load_cases()
    except Exception as exc:
        logger.error("case data could not be loaded (%s)", exc.__class__.__name__)
        raise ApiError(503, "CASES_UNAVAILABLE", "Case data could not be loaded.") from None
    items, skipped = [], 0
    for key in sorted(cases):
        case = cases[key]
        try:
            if not isinstance(case, Case):
                case = Case.model_validate(case)
            items.append(build_case_summary(case, source.focal_status(case.focal_correlation_id)).model_dump())
        except Exception:
            skipped += 1
    if skipped:
        logger.warning("skipped %d malformed case record(s)", skipped)
    return ok(items)


@router.post(
    "/diagnose", status_code=201, response_model=DiagnosisEnvelope, summary="Diagnose a case",
    description="Runs the team's diagnosis pipeline (app.uc4.pipeline.diagnose) on the case, checks the result "
                "against the agreed Diagnosis contract, saves it to the audit log (secrets masked) and returns "
                "the saved Diagnosis. No result is ever invented: if the pipeline is not available the answer is "
                "503 DIAGNOSIS_NOT_READY.",
    responses=_error_docs(
        (404, "CASE_NOT_FOUND"), (409, "DIAGNOSIS_CONFLICT: diagnosis_id already saved"),
        (422, "VALIDATION_ERROR: bad request body"),
        (502, "DIAGNOSIS_FAILED (pipeline raised an error) or DIAGNOSIS_INVALID (result breaks the contract)"),
        (503, "DIAGNOSIS_NOT_READY (no pipeline yet) or DATABASE_UNAVAILABLE"),
        (504, "DIAGNOSIS_TIMEOUT: the pipeline took too long; nothing was saved")),
)
async def diagnose(body: DiagnoseRequest, settings: ApiSettings = Depends(get_settings),
                   source: CaseSource = Depends(get_case_source),
                   pipeline: Optional[PipelineFn] = Depends(get_pipeline),
                   request_id: Optional[str] = Depends(get_request_id)) -> JSONResponse:
    try:
        case = source.load_cases().get(body.case_id)
    except Exception as exc:
        logger.error("case data could not be loaded (%s)", exc.__class__.__name__)
        raise ApiError(503, "CASES_UNAVAILABLE", "Case data could not be loaded.") from None
    if case is None:
        raise ApiError(404, "CASE_NOT_FOUND", "The requested case was not found.")
    if pipeline is None:
        raise ApiError(503, "DIAGNOSIS_NOT_READY", "The diagnosis service is not ready yet.")

    try:
        result = await asyncio.wait_for(asyncio.to_thread(pipeline, strip_labels(case)),
                                        timeout=settings.diagnose_timeout_s)
    except asyncio.TimeoutError:
        logger.warning("diagnosis timed out for %s after %ss", body.case_id, settings.diagnose_timeout_s)
        raise ApiError(504, "DIAGNOSIS_TIMEOUT", "The diagnosis took too long and was not saved.") from None
    except Exception as exc:
        logger.error("diagnosis pipeline failed for %s (%s)", body.case_id, exc.__class__.__name__)
        raise ApiError(502, "DIAGNOSIS_FAILED", "The diagnosis service failed for this case.") from None

    diagnosis = check_diagnosis(result, body.case_id)
    try:
        existing = audit.get_diagnosis(settings.audit_db_path, diagnosis["diagnosis_id"])
    except audit.AuditError as exc:
        raise _storage_error(exc) from None
    if existing is not None:
        raise ApiError(409, "DIAGNOSIS_CONFLICT", "A diagnosis with this id is already saved.")
    try:
        event = audit.record_diagnosis(settings.audit_db_path, diagnosis, request_id=request_id)
    except audit.AuditValidationError as exc:
        if "already recorded" in str(exc):
            raise ApiError(409, "DIAGNOSIS_CONFLICT", "A diagnosis with this id is already saved.") from None
        logger.warning("diagnosis could not be stored: %s", exc.__class__.__name__)
        raise ApiError(502, "DIAGNOSIS_INVALID", "The diagnosis service returned an invalid result.") from None
    except audit.AuditError as exc:
        raise _storage_error(exc) from None
    return ok(event["data"], status=201)


@router.get(
    "/diagnoses/{diagnosis_id}", response_model=DiagnosisEnvelope, summary="Get a saved diagnosis",
    description="Returns the saved Diagnosis exactly as stored (all fields, secrets masked). Never re-runs the pipeline.",
    responses=_error_docs((404, "DIAGNOSIS_NOT_FOUND"), (422, "VALIDATION_ERROR: bad id"),
                          (503, "DATABASE_UNAVAILABLE")),
)
def get_diagnosis(diagnosis_id: str = PathParam(pattern=ID_PATTERN),
                  settings: ApiSettings = Depends(get_settings)) -> JSONResponse:
    try:
        diagnosis = audit.get_diagnosis(settings.audit_db_path, diagnosis_id)
    except audit.AuditError as exc:
        raise _storage_error(exc) from None
    if diagnosis is None:
        raise ApiError(404, "DIAGNOSIS_NOT_FOUND", "The requested diagnosis was not found.")
    return ok(diagnosis)


@router.post(
    "/diagnoses/{diagnosis_id}/feedback", status_code=201, response_model=FeedbackEnvelope,
    summary="Add reviewer feedback",
    description="Appends one reviewer verdict (confirm / reject / annotate). Earlier feedback is never changed. "
                "'annotate' needs a note; cause_id, if given, must be a cause_id of this diagnosis; notes are "
                f"at most {MAX_NOTE_CHARS} characters and secrets in them are masked before saving.",
    responses=_error_docs((404, "DIAGNOSIS_NOT_FOUND"),
                          (422, "VALIDATION_ERROR (bad body) or UNKNOWN_CAUSE (cause_id not in this diagnosis)"),
                          (503, "DATABASE_UNAVAILABLE")),
)
def add_feedback(body: FeedbackRequest, diagnosis_id: str = PathParam(pattern=ID_PATTERN),
                 settings: ApiSettings = Depends(get_settings),
                 request_id: Optional[str] = Depends(get_request_id)) -> JSONResponse:
    try:
        diagnosis = audit.get_diagnosis(settings.audit_db_path, diagnosis_id)
    except audit.AuditError as exc:
        raise _storage_error(exc) from None
    if diagnosis is None:
        raise ApiError(404, "DIAGNOSIS_NOT_FOUND", "The requested diagnosis was not found.")
    if body.cause_id is not None and body.cause_id not in _cause_ids(diagnosis):
        raise ApiError(422, "UNKNOWN_CAUSE", "cause_id is not a cause of this diagnosis.")
    note = mask_text(body.note)[0] if body.note is not None else None
    try:
        record = audit.record_feedback(settings.audit_db_path, diagnosis_id, body.verdict,
                                       cause_id=body.cause_id, note=note, request_id=request_id)
    except audit.AuditNotFoundError:
        raise ApiError(404, "DIAGNOSIS_NOT_FOUND", "The requested diagnosis was not found.") from None
    except audit.AuditValidationError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from None
    except audit.AuditError as exc:
        raise _storage_error(exc) from None
    return ok(record, status=201)


@router.get(
    "/diagnoses/{diagnosis_id}/feedback", response_model=FeedbackListEnvelope, summary="List reviewer feedback",
    description="All feedback for one diagnosis, oldest first (append-only history).",
    responses=_error_docs((404, "DIAGNOSIS_NOT_FOUND"), (422, "VALIDATION_ERROR: bad id"),
                          (503, "DATABASE_UNAVAILABLE")),
)
def list_feedback(diagnosis_id: str = PathParam(pattern=ID_PATTERN),
                  settings: ApiSettings = Depends(get_settings)) -> JSONResponse:
    try:
        return ok(audit.get_feedback(settings.audit_db_path, diagnosis_id))
    except audit.AuditNotFoundError:
        raise ApiError(404, "DIAGNOSIS_NOT_FOUND", "The requested diagnosis was not found.") from None
    except audit.AuditError as exc:
        raise _storage_error(exc) from None


@router.get(
    "/audit/verify", response_model=ChainEnvelope, summary="Verify the audit chain",
    description="Recalculates every hash in the audit log. data.valid is false (with first_bad_seq and reason) "
                "if history was changed outside the application.",
    responses=_error_docs((503, "DATABASE_UNAVAILABLE")),
)
def verify_audit_chain(settings: ApiSettings = Depends(get_settings)) -> JSONResponse:
    try:
        return ok(audit.verify_chain(settings.audit_db_path))
    except audit.AuditError as exc:
        raise _storage_error(exc) from None


def readiness(settings: ApiSettings) -> dict[str, Any]:
    """Database and pipeline status for /health (no secrets, no paths)."""
    try:
        audit.init_db(settings.audit_db_path)
        database = "up"
    except audit.AuditError:
        database = "down"
    pipeline_fn, pipeline_status = resolve_pipeline()
    return {"api": "up", "database": database,
            "pipeline": "ready" if pipeline_fn is not None else "not_ready",
            "pipeline_detail": pipeline_status}


def _is_valid_request_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,63}", value))

"""FastAPI app: request IDs, the {ok, request_id, data, error} envelope, CORS and routes."""
import logging
import time
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.config import get_policy, get_settings
from app.contracts import Envelope, ErrorInfo, FeedbackIn, Outcome, SearchRequest, TicketIn
from app.db.repository import add_feedback, get_analysis, list_analyses, save_analysis, stats
from app.db.session import db_status, dialect, ensure_tables, mask, set_db_status
from app.llm.base import LLMClient
from app.llm.router import build_llm
from app.pipeline.gate import retrieval_threshold
from app.pipeline.orchestrator import analyse
from app.pipeline.redact import redact
from app.pipeline.embed import embedder_name
from app.pipeline.retrieve import get_index, index_built
from app.warmup import is_ready, start_warm_up, warm_up_started

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ticket-assistant")


def db_error_text(exc: Exception) -> str:
    """First line of a database error, with the URL and host masked. Safe to log."""
    return mask(f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}")[:300]


@asynccontextmanager
async def lifespan(app: FastAPI):
    retrieval_threshold(get_policy())  # fail at startup if the embedder has no tuned gate threshold
    # load models and index in the background; the server answers /health meanwhile (see app/warmup.py)
    start_warm_up()
    # create the audit tables at startup (no Alembic). An unreachable database must not stop the app:
    # analyses still work (flagged AUDIT_WRITE_FAILED) and the tables are retried on the next use.
    try:
        ensure_tables()
        log.info("database ok (%s)", dialect())
    except Exception as e:
        log.error("database unavailable at startup (%s): %s", dialect(), db_error_text(e))
    yield


app = FastAPI(title="Ticket Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_methods=["*"], allow_headers=["*"])


@lru_cache
def get_llm() -> LLMClient | None:
    """Gemini -> Groq chain built once from env settings. None means extractive (no LLM)."""
    return build_llm(get_settings())


def ok(request: Request, data) -> dict:
    return Envelope(ok=True, request_id=request.state.request_id, data=data).model_dump()


def fail(request: Request, status: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    body = Envelope(ok=False, request_id=getattr(request.state, "request_id", "unknown"),
                    error=ErrorInfo(code=code, message=message, retryable=retryable))
    return JSONResponse(status_code=status, content=body.model_dump())


@app.middleware("http")
async def request_id_and_timing(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    log.info("%s %s %s %.0fms id=%s", request.method, request.url.path, response.status_code,
             (time.perf_counter() - start) * 1000, request.state.request_id)
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    return fail(request, 422, "VALIDATION_ERROR", f"{'.'.join(map(str, first['loc']))}: {first['msg']}")


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: OperationalError):
    set_db_status(False)
    log.error("database unavailable (%s) id=%s: %s", dialect(), getattr(request.state, "request_id", "?"),
              db_error_text(exc))
    return fail(request, 503, "DATABASE_UNAVAILABLE",
                "The audit log database can't be reached right now. Try again shortly.", retryable=True)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.exception("unhandled error id=%s", getattr(request.state, "request_id", "?"))
    return fail(request, 500, "INTERNAL_ERROR", "Something went wrong. Quote the request_id when reporting.", True)


@app.get("/health")
def health(request: Request):
    # Must stay fast and return 200 while warming up (Render's health check): never wait for the index
    # while warm-up builds it. Without a warm-up (no lifespan, e.g. scripts) build it here as before.
    docs = len(get_index().docs) if index_built() or not warm_up_started() else None
    llm = get_llm()
    # last known database state, so /health stays fast even when the database is down
    return ok(request, {"status": "ok", "ready": is_ready(), "documents_indexed": docs, "embedder": embedder_name(),
                        "llm_chain": [p.name for p in llm.providers] if llm else ["extractive"],
                        "database": "ok" if db_status() == "ok" else "unavailable",
                        "database_dialect": dialect()})


@app.post("/api/analyze")
def analyze_ticket(ticket: TicketIn, request: Request):
    result = analyse(ticket, get_llm())
    try:
        save_analysis(result, ticket, request.state.request_id)
        set_db_status(True)
    except OperationalError as e:
        set_db_status(False)
        log.error("audit write failed, database unavailable (%s) id=%s analysis_id=%s: %s", dialect(),
                  request.state.request_id, result.analysis_id, db_error_text(e))
        result.reasons.append("AUDIT_WRITE_FAILED")
    except Exception:
        # the analyst still gets the result; the missing audit row is flagged, not hidden
        log.exception("audit write failed id=%s analysis_id=%s", request.state.request_id, result.analysis_id)
        result.reasons.append("AUDIT_WRITE_FAILED")
    return ok(request, result.model_dump())


@app.get("/api/analyses")
def analyses(request: Request, outcome: Optional[Outcome] = None, limit: int = Query(50, ge=1, le=200)):
    rows = list_analyses(outcome, limit)
    set_db_status(True)
    return ok(request, [a.model_dump() for a in rows])


# A database error in the endpoints below becomes 503 DATABASE_UNAVAILABLE (see database_unavailable);
# reaching the end of one means the database answered, so /health can report it as ok again.
@app.get("/api/analyses/{analysis_id}")
def analysis_detail(analysis_id: str, request: Request):
    record = get_analysis(analysis_id)
    set_db_status(True)
    if record is None:
        return fail(request, 404, "NOT_FOUND", f"No analysis with id {analysis_id}")
    return ok(request, record.model_dump())


@app.post("/api/analyses/{analysis_id}/feedback")
def feedback(analysis_id: str, fb: FeedbackIn, request: Request):
    record = get_analysis(analysis_id)
    set_db_status(True)
    if record is None:
        return fail(request, 404, "NOT_FOUND", f"No analysis with id {analysis_id}")
    if fb.target.startswith("match:"):
        source_id = fb.target.removeprefix("match:")
        if source_id not in {m.source_id for m in record.matches}:
            return fail(request, 422, "VALIDATION_ERROR", f"target: {source_id} is not a match of this analysis")
    return ok(request, add_feedback(analysis_id, fb).model_dump())


@app.get("/api/stats")
def get_stats(request: Request):
    result = stats()
    set_db_status(True)
    return ok(request, result.model_dump())


@app.post("/api/search")
def search(req: SearchRequest, request: Request):
    query, _ = redact(req.query)
    hits = get_index().search(query, top_k=req.top_k, filters=req.filters)
    # `coverage` keeps its meaning (keyword coverage); the cosine is in each match's metadata
    return ok(request, [dict(**m.model_dump(), coverage=m.metadata["coverage"]) for m, _ in hits])

"""Shared shapes for UC4: a failure case and one piece of evidence."""
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.uc4.report_models import Finding, Report


class Case(BaseModel):
    """One failure case, with the field names of cases.jsonl.

    Only the first block is needed to diagnose. The label block is optional,
    so a live case (no labels) works too. Evidence code must not read labels.
    """

    model_config = ConfigDict(extra="ignore")

    # What we know about the failure.
    case_id: str
    focal_correlation_id: str
    route: str
    onset_ts: datetime
    window_start: datetime
    window_end: datetime

    # Labels and bookkeeping (dataset only).
    split: Optional[str] = None
    difficulty: Optional[str] = None
    expected_class: Optional[str] = None
    expected_cause: Optional[str] = None
    expected_first_check: Optional[str] = None
    expected_outcome: Optional[str] = None
    requires_escalation: Optional[bool] = None
    culprit_dependency: Optional[str] = None
    culprit_client: Optional[str] = None
    missing_info: list[str] = Field(default_factory=list)
    worked_example: Optional[bool] = None
    human_verify_suggested: Optional[bool] = None
    summary: Optional[str] = None
    generation: Optional[dict[str, Any]] = None


EvidenceKind = Literal["request", "traffic", "metric", "change", "doc", "missing"]


class EvidenceItem(BaseModel):
    """One finding: a stable id, a kind, one readable line, and its raw numbers."""

    id: str  # stable, e.g. "request:c-1e93f5b875", "metric:service:orders-db"
    kind: EvidenceKind
    text: str  # one line a human (and the LLM) can read, with numbers
    data: dict[str, Any] = Field(default_factory=dict)  # the same numbers, machine-readable


CauseStatus = Literal["likely", "probable", "unsupported"]


class SignalLink(BaseModel):
    """One yes/no signal and why it counts for or against a cause."""

    signal: str  # e.g. "token_age_over_ttl"
    present: bool  # True = signal is on; False = an expected key signal is absent
    ratio: float  # P(signal value | this cause) / average over the other causes; > 1 favours this cause
    evidence_ids: list[str] = Field(default_factory=list)  # EvidenceItem ids that show it


class RankedCause(BaseModel):
    """One candidate cause, ranked by naive Bayes. Never "confirmed": a human confirms by running first_check."""

    rank: int  # 1 = most likely
    cause: str  # e.g. "token_expired"
    failure_class: str  # e.g. "authentication"
    confidence: float  # posterior with equal priors; sums to 1 over all causes
    status: CauseStatus  # likely: all confirming signals + confidence >= threshold + no near-tie; see rank.py
    near_tie: bool  # within the margin of the top cause, with at least one other cause also there
    supporting: list[SignalLink] = Field(default_factory=list)
    contradicting: list[SignalLink] = Field(default_factory=list)
    confirming_seen: list[str] = Field(default_factory=list)
    confirming_missing: list[str] = Field(default_factory=list)
    first_check: Optional[str] = None
    escalate: bool = False  # the fix needs a privileged change by its owner (the checks themselves are read-only)
    missing_info: list[str] = Field(default_factory=list)  # from the "missing" evidence items


Outcome = Literal["RECOMMEND", "CLARIFY"]


class DistinguishingSignal(BaseModel):
    """A signal whose likelihood differs a lot between tied causes: checking it helps tell them apart."""

    signal: str
    favours: str  # the tied cause under which this signal is most likely to be on
    p_on: dict[str, float]  # P(signal on | cause) for each tied cause
    observed: Optional[bool] = None  # its value in this case (None = unknown)


class TellApart(BaseModel):
    """How to tell near-tied causes apart: each one's first check, and the signals that differ between them."""

    causes: list[str]
    first_checks: dict[str, Optional[str]]
    signals: list[DistinguishingSignal] = Field(default_factory=list)
    note: str  # one readable line


class GateDecision(BaseModel):
    """What the pipeline does next: recommend (maybe with alternatives), or ask for the missing information."""

    outcome: Outcome
    escalate: bool  # RECOMMEND and, for the top cause, the fix needs a privileged change by its owner (the checks themselves are read-only)
    top_cause: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)  # why CLARIFY (empty for RECOMMEND)
    missing_info: list[str] = Field(default_factory=list)
    low_confidence: bool = False  # RECOMMEND, but the top confidence is below the threshold
    alternatives: list[str] = Field(default_factory=list)  # every near-tie cause, top first (empty if clear winner)
    tell_apart: Optional[TellApart] = None  # set when alternatives are listed


class TraceStep(BaseModel):
    """One pipeline step: what ran, how long it took, and a short note (never a secret)."""

    step: str  # e.g. "collect_evidence"
    ms: float
    detail: str = ""


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Diagnosis(BaseModel):
    """Everything the API returns for one case. JSON-ready: diagnosis.model_dump_json().

    On CLARIFY no cause is claimed anywhere: ranked is empty, failure_class is None, the report has no causes.
    """

    diagnosis_id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_now)
    case_id: str
    route: str
    onset_ts: datetime

    outcome: Outcome  # RECOMMEND | CLARIFY
    escalate: bool  # for the top cause, the fix needs a privileged change by its owner (the checks themselves are read-only)
    failure_class: Optional[str] = None  # the top cause's class
    class_confidence: Optional[float] = None  # sum of confidence over that class's causes

    ranked: list[RankedCause] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)  # near-tie causes, top first (from the gate)
    tell_apart: Optional[TellApart] = None  # how to tell the alternatives apart (from the gate)

    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)

    report: Optional[Report] = None  # after apply_findings: blocked parts removed
    report_findings: list[Finding] = Field(default_factory=list)  # check_report on the report as written
    groundedness: Optional[float] = None  # verified citations / all citations, as written; None if nothing cited
    generator: str = "template"  # "template" until an LLM writes the report

    trace: list[TraceStep] = Field(default_factory=list)

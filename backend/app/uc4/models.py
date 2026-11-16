"""Shared shapes for UC4: a failure case and one piece of evidence."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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


EvidenceKind = Literal["request", "traffic", "metric", "change", "missing"]


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
    status: CauseStatus  # likely: all confirming signals + confidence >= threshold; probable: confidence >= threshold
    near_tie: bool  # confidence within the margin of the next or previous cause
    supporting: list[SignalLink] = Field(default_factory=list)
    contradicting: list[SignalLink] = Field(default_factory=list)
    confirming_seen: list[str] = Field(default_factory=list)
    confirming_missing: list[str] = Field(default_factory=list)
    first_check: Optional[str] = None
    escalate: bool = False  # the first check needs privileged access
    missing_info: list[str] = Field(default_factory=list)  # from the "missing" evidence items


Outcome = Literal["RECOMMEND", "CLARIFY"]


class GateDecision(BaseModel):
    """What the pipeline does next: recommend the top cause, or ask for the missing information."""

    outcome: Outcome
    escalate: bool  # RECOMMEND and the top cause's first check needs privileged access
    top_cause: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)  # why CLARIFY (empty for RECOMMEND)
    missing_info: list[str] = Field(default_factory=list)

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

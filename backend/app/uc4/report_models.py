"""The shape of the UC4 report the LLM writes, and of the findings checks.py returns.

The LLM fills a Report; checks.py checks it against the evidence before anyone sees it.
Causes are never "confirmed": likelihood is only likely / probable / possible.
"""
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A piece of evidence the report relies on: its id and a quote copied from its text."""

    evidence_id: str  # an EvidenceItem.id, e.g. "metric:service:orders-db"
    quote: str  # must be copied from that item's text (checks.py verifies it)


class ReportCause(BaseModel):
    """One cause from the ranked list, explained, with the evidence for and against it."""

    cause: str  # must be one of the ranked causes code gave the LLM, e.g. "upstream_dependency_slow"
    likelihood: Literal["likely", "probable", "possible"]
    explanation: str
    supporting: list[Citation]
    contradicting: list[Citation] = Field(default_factory=list)


class Step(BaseModel):
    """A read-only verification step (look, compare, query). Anything that changes a system
    (restart, rotate, roll back...) belongs in Escalation, not here."""

    action: str
    why: str
    cites: list[str] = Field(default_factory=list)  # evidence ids this step relies on


class Escalation(BaseModel):
    needed: bool
    team: str = ""
    reason: str = ""  # may mention privileged actions (restart, rotate...): a human decides


class Report(BaseModel):
    case_id: str
    outcome: Literal["RECOMMEND", "CLARIFY", "ESCALATE"]
    summary: str
    causes: list[ReportCause]
    verification_steps: list[Step]
    escalation: Escalation
    missing_info: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """One problem found by a check. "block" means the part at `where` must not be shown."""

    code: str  # e.g. "CITE_QUOTE_NOT_FOUND"
    severity: Literal["info", "warn", "block"]
    message: str  # never contains a secret
    where: str  # path in the report, e.g. "causes[0].supporting[1]", "summary"

"""API contract: every request and response shape. The frontend mirrors this file.
Change a field name here only on purpose, and update the frontend in the same PR."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Outcome = Literal["RECOMMEND", "CLARIFY", "ESCALATE"]


# ---------- input ----------
class TicketIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    application: Optional[str] = None
    environment: Optional[Literal["prod", "uat"]] = None


class SearchFilters(BaseModel):
    category: Optional[str] = None
    application: Optional[str] = None
    assignment_group: Optional[str] = None
    environment: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[str] = None  # ISO date, inclusive
    date_to: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    filters: SearchFilters = SearchFilters()
    top_k: int = Field(default=10, ge=1, le=50)


# ---------- pipeline outputs ----------
class Classification(BaseModel):
    category: str
    subcategory: str
    priority: str
    confidence: float  # 0..1
    method: str        # which classifier produced this, e.g. "knn_vote" or "calibrated_logreg"


class Match(BaseModel):
    source_id: str     # INC... or KB...
    source_type: Literal["ticket", "kb"]
    title: str
    text: str          # what can be cited: resolution notes or KB steps
    score: float       # retrieval score used for ranking
    metadata: dict[str, Any] = {}


class Citation(BaseModel):
    source_id: str
    excerpt: str       # must appear word-for-word in the source text
    reason: str        # why this source supports the step


class Recommendation(BaseModel):
    steps: list[str]
    citations: list[Citation]
    generator: str     # "gemini", "groq", "extractive" or "fake"


class AuditEvent(BaseModel):
    step: str
    detail: dict[str, Any]


class AnalysisResult(BaseModel):
    analysis_id: str
    redacted_text: str
    redactions: dict[str, int]          # e.g. {"email": 1}
    classification: Classification
    matches: list[Match]
    recommendation: Optional[Recommendation]  # None when escalated before generation
    outcome: Outcome
    reasons: list[str]                  # machine-readable reason codes
    confidence: float                   # min of the independent signals
    signals: dict[str, float]           # each signal, shown to the analyst
    trace: list[AuditEvent]


# ---------- audit log + analyst feedback ----------
Verdict = Literal["useful", "incorrect", "unresolved"]


class FeedbackIn(BaseModel):
    verdict: Verdict
    target: str = Field(pattern=r"^(recommendation|match:[A-Za-z0-9_-]+)$")  # "recommendation" or "match:<source_id>"
    comment: Optional[str] = Field(default=None, max_length=2000)
    reviewer: Optional[str] = Field(default=None, max_length=100)


class FeedbackOut(BaseModel):
    id: str
    analysis_id: str
    verdict: Verdict
    target: str
    comment: Optional[str]              # stored redacted
    reviewer: Optional[str]
    created_at: str                     # ISO 8601, UTC


class AnalysisSummary(BaseModel):
    analysis_id: str
    created_at: str
    title: str                          # redacted
    category: str
    priority: str
    outcome: Outcome
    confidence: float
    generator: Optional[str]            # None when the gate stopped the ticket before generation


class AnalysisRecord(BaseModel):
    analysis_id: str
    created_at: str
    request_id: str
    title: str                          # redacted
    description: str                    # redacted
    category: str
    subcategory: str
    priority: str
    classifier_confidence: float
    outcome: Outcome
    confidence: float
    reasons: list[str]
    signals: dict[str, float]
    recommendation: Optional[Recommendation]
    matches: list[Match]
    trace: list[AuditEvent]
    generator: Optional[str]
    feedback: list[FeedbackOut]


class Stats(BaseModel):
    total_analyses: int
    by_outcome: dict[str, int]
    by_verdict: dict[str, int]
    generator_share: dict[str, float]   # share of analyses per generator; "none" = stopped before generation


# ---------- envelope ----------
class ErrorInfo(BaseModel):
    code: str
    message: str
    retryable: bool = False


class Envelope(BaseModel):
    ok: bool
    request_id: str
    data: Optional[Any] = None
    error: Optional[ErrorInfo] = None

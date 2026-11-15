"""Reads and writes for the audit log.

Append-only on purpose: this module only inserts and selects. There is no update or delete
function anywhere, so a stored analysis or verdict can never be changed after the fact.
Every text column is redacted here, at the boundary, so nothing raw can reach the database."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.contracts import (AnalysisRecord, AnalysisResult, AnalysisSummary, FeedbackIn, FeedbackOut, Stats,
                           TicketIn)
from app.db.models import Analysis, Feedback
from app.db.session import get_sessionmaker
from app.pipeline.redact import redact


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:  # SQLite drops the timezone; we always store UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _feedback_out(f: Feedback) -> FeedbackOut:
    return FeedbackOut(id=f.id, analysis_id=f.analysis_id, verdict=f.verdict, target=f.target,
                       comment=f.comment, reviewer=f.reviewer, created_at=_iso(f.created_at))


def save_analysis(result: AnalysisResult, ticket: TicketIn, request_id: str) -> None:
    cls = result.classification
    row = Analysis(
        id=result.analysis_id, request_id=request_id,
        title=redact(ticket.title)[0], description=redact(ticket.description)[0],
        category=cls.category, subcategory=cls.subcategory, priority=cls.priority,
        classifier_confidence=cls.confidence, outcome=result.outcome, confidence=result.confidence,
        reasons=list(result.reasons), signals=dict(result.signals),
        recommendation=result.recommendation.model_dump() if result.recommendation else None,
        matches=[m.model_dump() for m in result.matches], trace=[e.model_dump() for e in result.trace],
        generator=result.recommendation.generator if result.recommendation else None)
    with get_sessionmaker()() as s, s.begin():
        s.add(row)


def list_analyses(outcome: str | None, limit: int) -> list[AnalysisSummary]:
    q = select(Analysis).order_by(Analysis.created_at.desc()).limit(limit)
    if outcome:
        q = q.where(Analysis.outcome == outcome)
    with get_sessionmaker()() as s:
        return [AnalysisSummary(analysis_id=a.id, created_at=_iso(a.created_at), title=a.title,
                                category=a.category, priority=a.priority, outcome=a.outcome,
                                confidence=a.confidence, generator=a.generator)
                for a in s.scalars(q)]


def get_analysis(analysis_id: str) -> AnalysisRecord | None:
    with get_sessionmaker()() as s:
        a = s.get(Analysis, analysis_id)
        if a is None:
            return None
        fb = s.scalars(select(Feedback).where(Feedback.analysis_id == analysis_id)
                       .order_by(Feedback.created_at)).all()
        return AnalysisRecord(
            analysis_id=a.id, created_at=_iso(a.created_at), request_id=a.request_id, title=a.title,
            description=a.description, category=a.category, subcategory=a.subcategory, priority=a.priority,
            classifier_confidence=a.classifier_confidence, outcome=a.outcome, confidence=a.confidence,
            reasons=a.reasons, signals=a.signals, recommendation=a.recommendation, matches=a.matches,
            trace=a.trace, generator=a.generator, feedback=[_feedback_out(f) for f in fb])


def add_feedback(analysis_id: str, fb: FeedbackIn) -> FeedbackOut:
    row = Feedback(analysis_id=analysis_id, verdict=fb.verdict, target=fb.target,
                   comment=redact(fb.comment)[0] if fb.comment else None,  # analysts may paste emails
                   reviewer=fb.reviewer)
    with get_sessionmaker()() as s, s.begin():
        s.add(row)
    return _feedback_out(row)


def stats() -> Stats:
    with get_sessionmaker()() as s:
        by_outcome = dict(s.execute(select(Analysis.outcome, func.count()).group_by(Analysis.outcome)).all())
        by_verdict = dict(s.execute(select(Feedback.verdict, func.count()).group_by(Feedback.verdict)).all())
        by_generator = s.execute(select(Analysis.generator, func.count()).group_by(Analysis.generator)).all()
    total = sum(by_outcome.values())
    share = {(g or "none"): round(n / total, 3) for g, n in by_generator} if total else {}
    return Stats(total_analyses=total, by_outcome=by_outcome, by_verdict=by_verdict, generator_share=share)

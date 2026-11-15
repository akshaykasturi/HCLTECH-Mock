"""Runs the six steps in order and records an audit event for each one."""
import uuid

from app.config import get_policy
from app.contracts import AnalysisResult, AuditEvent, TicketIn
from app.llm.base import LLMClient
from app.pipeline import gate
from app.pipeline.classify import classify
from app.pipeline.generate import generate
from app.pipeline.redact import redact
from app.pipeline.retrieve import get_index
from app.pipeline.verify import route, verify_citations


def analyse(ticket: TicketIn, llm: LLMClient | None) -> AnalysisResult:
    policy = get_policy()
    trace: list[AuditEvent] = []

    # 1 redact
    text, redactions = redact(f"{ticket.title}. {ticket.description}")
    trace.append(AuditEvent(step="redact", detail={"redactions": redactions}))

    # 2 classify
    cls = classify(text)
    if gate.safety_hit(text, policy):  # same whole-word matching as the gate
        cls = cls.model_copy(update={"priority": "P1"})  # safety rule overrides the model
    trace.append(AuditEvent(step="classify", detail=cls.model_dump()))

    # 3 retrieve
    index = get_index()
    hits = index.search(text, top_k=policy["retrieval"]["top_k"])
    matches = [m for m, _ in hits]
    strength = hits[0][1] if hits else 0.0  # cosine similarity to the best fused match
    trace.append(AuditEvent(step="retrieve", detail={
        "top_ids": [m.source_id for m in matches], "retrieval_strength": strength,
        "embedder": index.embedder.name,
        "keyword_coverage": matches[0].metadata["coverage"] if matches else 0.0}))  # diagnostic only

    # 4 gate (before any LLM call)
    reasons = gate.check(text, strength, policy)
    stopped = gate.stop_outcome(reasons)
    trace.append(AuditEvent(step="gate", detail={"reasons": reasons, "stopped": stopped}))

    signals = {"classifier": cls.confidence, "retrieval": strength}
    if stopped:
        return AnalysisResult(
            analysis_id=str(uuid.uuid4()), redacted_text=text, redactions=redactions, classification=cls,
            matches=matches, recommendation=None, outcome=stopped, reasons=reasons,
            confidence=round(min(signals.values()), 3), signals=signals, trace=trace)

    # 5 generate
    rec, fallback, llm_errors = generate(text, matches, llm)
    if fallback:
        reasons.append(fallback)
    trace.append(AuditEvent(step="generate", detail={"generator": rec.generator, "steps": len(rec.steps),
                                                     "fallback": fallback, "llm_errors": llm_errors}))

    # 6 verify + route
    total = len(rec.citations)
    rec, dropped = verify_citations(rec, matches)
    grounding = round(len(rec.citations) / total, 3) if total else 0.0
    if dropped:
        reasons.append(f"CITATIONS_DROPPED:{dropped}")
    outcome, route_reasons, confidence = route(cls.confidence, strength, grounding, len(rec.citations), policy)
    reasons += route_reasons
    signals["grounding"] = grounding
    trace.append(AuditEvent(step="verify", detail={"kept": len(rec.citations), "dropped": dropped,
                                                   "outcome": outcome}))

    return AnalysisResult(
        analysis_id=str(uuid.uuid4()), redacted_text=text, redactions=redactions, classification=cls,
        matches=matches, recommendation=rec, outcome=outcome, reasons=reasons,
        confidence=confidence, signals=signals, trace=trace)

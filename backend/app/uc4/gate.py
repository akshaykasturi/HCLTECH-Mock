"""The CLARIFY gate: decide whether we may recommend a cause at all.

Naive Bayes always picks a winner, even when half the evidence is missing (the data card shows
it 0.6-0.99 sure on the insufficient cases). So code checks first, and asks for what is missing
instead of guessing. No LLM call happens on CLARIFY.
"""
from typing import Optional

from app.uc4.models import EvidenceItem, GateDecision, RankedCause
from app.uc4.settings import get_settings


def decide(ranked: list[RankedCause], signals: dict[str, Optional[bool]],
           evidence: list[EvidenceItem], threshold: Optional[float] = None) -> GateDecision:
    """CLARIFY if evidence is missing, a missing-data signal is on, or the top cause is not confident enough.
    Otherwise RECOMMEND, with escalate=True when the top cause's first check needs privileged access.
    `threshold` overrides settings.yaml (used by scripts/tune_rank.py)."""
    cfg = get_settings()["rank"]
    threshold = cfg["confidence_threshold"] if threshold is None else threshold
    missing_items = [item for item in evidence if item.kind == "missing"]
    missing_info = [item.text.removeprefix("Missing: ") for item in missing_items]
    top = ranked[0] if ranked else None

    reasons = []
    if missing_items:
        reasons.append("missing evidence: " + ", ".join(item.id for item in missing_items))
    flagged = [s for s in cfg["clarify_signals"] if signals.get(s)]
    if flagged:
        reasons.append("missing-data signals on: " + ", ".join(flagged))
        missing_info += [f"data behind signal {s}" for s in flagged if not missing_items]
    if top is None:
        reasons.append("no cause could be ranked")
    elif top.confidence < threshold:
        reasons.append(f"top cause {top.cause} confidence {top.confidence:.2f} is below the threshold {threshold}")

    if reasons:
        return GateDecision(outcome="CLARIFY", escalate=False, top_cause=top.cause if top else None,
                            reasons=reasons, missing_info=missing_info)
    return GateDecision(outcome="RECOMMEND", escalate=top.escalate, top_cause=top.cause)

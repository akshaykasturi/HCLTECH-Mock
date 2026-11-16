"""The gate: recommend, or ask for what is missing.

CLARIFY only when evidence is actually missing: a "missing" evidence item, or a missing-data signal
(settings.yaml: rank.clarify_signals). Naive Bayes always picks a winner even with half the evidence gone,
so these rules run before any confidence is looked at. No LLM call happens on CLARIFY.

Low confidence alone is NOT a reason to CLARIFY: the evidence is complete, asking for more would not help.
Instead we RECOMMEND and say it is not a clear win: every near-tie cause is listed, with each one's
first check and the signals that differ between them, so the engineer knows how to tell them apart.
"""
from typing import Optional

from app.uc4.models import EvidenceItem, GateDecision, RankedCause, TellApart
from app.uc4.rank import distinguishing_signals
from app.uc4.settings import get_settings


def missing_evidence(signals: dict[str, Optional[bool]], evidence: list[EvidenceItem]) -> tuple[list[str], list[str]]:
    """(reasons, missing_info) when evidence is missing; both empty when evidence is complete."""
    cfg = get_settings()["rank"]
    missing_items = [item for item in evidence if item.kind == "missing"]
    missing_info = [item.text.removeprefix("Missing: ") for item in missing_items]
    reasons = []
    if missing_items:
        reasons.append("missing evidence: " + ", ".join(item.id for item in missing_items))
    flagged = [s for s in cfg["clarify_signals"] if signals.get(s)]
    if flagged:
        reasons.append("missing-data signals on: " + ", ".join(flagged))
        if not missing_items:
            missing_info += [f"data behind signal {s}" for s in flagged]
    return reasons, missing_info


def tell_apart(candidates: list[RankedCause], signals: dict[str, Optional[bool]]) -> TellApart:
    """Each candidate's first check, and the signals that differ most between the candidates."""
    cfg = get_settings()["rank"]
    names = [c.cause for c in candidates]
    diffs = distinguishing_signals(names, signals, cfg["tell_apart_min_spread"], cfg["tell_apart_max_signals"])
    checks = "; ".join(f"{c.cause} ({c.confidence:.2f}): run {c.first_check}" for c in candidates)
    seen = {True: "on", False: "off", None: "unknown"}
    differ = "; ".join(f"{d.signal} (most likely under {d.favours}; here {seen[d.observed]})" for d in diffs)
    note = f"Not a clear winner. To tell them apart: {checks}. Signals that differ: {differ or 'none'}."
    return TellApart(causes=names, first_checks={c.cause: c.first_check for c in candidates},
                     signals=diffs, note=note)


def decide(ranked: list[RankedCause], signals: dict[str, Optional[bool]],
           evidence: list[EvidenceItem], threshold: Optional[float] = None) -> GateDecision:
    """CLARIFY if evidence is missing. Otherwise RECOMMEND the top cause; when it is below the threshold
    or near-tied, also list the alternatives and how to tell them apart.
    `threshold` overrides settings.yaml (used by scripts/tune_rank.py)."""
    cfg = get_settings()["rank"]
    threshold = cfg["confidence_threshold"] if threshold is None else threshold
    top = ranked[0] if ranked else None

    reasons, missing_info = missing_evidence(signals, evidence)
    if top is None:
        reasons.append("no cause could be ranked")
    if reasons:
        return GateDecision(outcome="CLARIFY", escalate=False, top_cause=top.cause if top else None,
                            reasons=reasons, missing_info=missing_info)

    low_confidence = top.confidence < threshold
    candidates = [r for r in ranked if r.near_tie]
    if low_confidence and len(candidates) < 2 and len(ranked) > 1:
        candidates = ranked[:2]  # no tie within the margin, but not sure either: show the runner-up
    if len(candidates) < 2:
        return GateDecision(outcome="RECOMMEND", escalate=top.escalate, top_cause=top.cause)
    return GateDecision(outcome="RECOMMEND", escalate=top.escalate, top_cause=top.cause,
                        low_confidence=low_confidence, alternatives=[c.cause for c in candidates],
                        tell_apart=tell_apart(candidates, signals))

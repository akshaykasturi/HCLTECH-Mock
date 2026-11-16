"""Run the code-only part of the pipeline for one case: evidence -> signals -> rank -> gate."""
from dataclasses import dataclass
from typing import Optional

from app.uc4.evidence import collect_evidence
from app.uc4.gate import decide
from app.uc4.models import Case, EvidenceItem, GateDecision, RankedCause
from app.uc4.rank import rank_causes
from app.uc4.signals import get_signals


@dataclass
class Diagnosis:
    case: Case
    evidence: list[EvidenceItem]
    signals: dict[str, Optional[bool]]
    ranked: list[RankedCause]
    decision: GateDecision


def diagnose(case: Case) -> Diagnosis:
    evidence = collect_evidence(case)
    signals = get_signals(case)
    ranked = rank_causes(signals, evidence)
    return Diagnosis(case, evidence, signals, ranked, decide(ranked, signals, evidence))

"""Rank likely causes with naive Bayes, and say which evidence supports or contradicts each.

Naive Bayes in one line: score(cause) = product over signals of P(signal value | cause),
with equal priors; then scale the scores so they sum to 1 (= confidence).
We add logs instead of multiplying, so 47 small numbers don't underflow to 0.

Inputs: signals (yes/no per signal name) and the case's evidence items (for citations and missing_info).
Model:  P(signal | cause) from derived/likelihoods.learned.yaml (learned on train),
        catalog (class, first_check, key/confirming signals) from causes.yaml.
"""
import math
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.uc4.models import EvidenceItem, RankedCause, SignalLink
from app.uc4.settings import BACKEND_DIR, get_settings

LIKELIHOODS = BACKEND_DIR / "data" / "eval" / "uc4" / "derived" / "likelihoods.learned.yaml"
CATALOG = Path(__file__).with_name("causes.yaml")


@lru_cache(maxsize=1)
def load_likelihoods() -> dict[str, dict[str, float]]:
    """P(signal is on | cause), as {cause: {signal: p}}."""
    return yaml.safe_load(LIKELIHOODS.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict[str, Any]]:
    """{cause: {class, first_check, requires_escalation, key_signals, confirming_signals}}."""
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))


# ---------- the maths ----------

def _p_value(p_on: float, on: bool) -> float:
    """P(observed value | cause): p if the signal is on, 1 - p if it is off."""
    return p_on if on else 1.0 - p_on


def posteriors(signals: dict[str, Optional[bool]]) -> dict[str, float]:
    """Naive Bayes with equal priors. Signals that are None (unknown) are skipped."""
    likelihoods = load_likelihoods()
    log_scores = {}
    for cause, table in likelihoods.items():
        log_scores[cause] = sum(math.log(_p_value(table[s], on))
                                for s, on in signals.items() if on is not None and s in table)
    # Normalise in log space: subtract the max before exp() so the biggest score becomes exp(0) = 1.
    top = max(log_scores.values())
    weights = {c: math.exp(v - top) for c, v in log_scores.items()}
    total = sum(weights.values())
    return {c: w / total for c, w in weights.items()}


def ratio(cause: str, signal: str, on: bool) -> float:
    """How much this signal value favours `cause` over the others:
    P(value | cause) / average P(value | other cause). > 1 = favours cause, < 1 = favours others."""
    likelihoods = load_likelihoods()
    others = [c for c in likelihoods if c != cause]
    mine = _p_value(likelihoods[cause][signal], on)
    theirs = sum(_p_value(likelihoods[o][signal], on) for o in others) / len(others)
    return round(mine / theirs, 2)


# ---------- signal -> evidence ----------

def evidence_for(signal: str, evidence: list[EvidenceItem]) -> list[str]:
    """Ids of the evidence items that show this signal (mapping in settings.yaml: signal_evidence)."""
    for pattern, prefixes in get_settings()["signal_evidence"]:
        if fnmatch(signal, pattern):
            ids = []
            for item in evidence:
                if not any(item.id.startswith(p) for p in prefixes):
                    continue
                if item.kind == "change" and not item.data.get("related"):
                    continue  # unrelated deploys are not evidence for "recent_deploy"
                ids.append(item.id)
            return ids
    return []


# ---------- ranking ----------

def rank_causes(signals: dict[str, Optional[bool]], evidence: list[EvidenceItem]) -> list[RankedCause]:
    """All causes, most likely first, each with supporting/contradicting signals and a status."""
    cfg = get_settings()["rank"]
    threshold, margin, min_ratio = cfg["confidence_threshold"], cfg["near_tie_margin"], cfg["min_ratio"]
    catalog = load_catalog()
    post = posteriors(signals)
    order = sorted(post, key=lambda c: (-post[c], c))
    missing_info = [item.text.removeprefix("Missing: ") for item in evidence if item.kind == "missing"]
    on_signals = [s for s, v in signals.items() if v]

    ranked = []
    for i, cause in enumerate(order):
        entry = catalog.get(cause, {})
        conf = post[cause]

        supporting, contradicting = [], []
        for s in on_signals:
            if s not in load_likelihoods()[cause]:
                continue
            r = ratio(cause, s, True)
            link = SignalLink(signal=s, present=True, ratio=r, evidence_ids=evidence_for(s, evidence))
            if r > min_ratio:
                supporting.append(link)
            elif r < 1 / min_ratio:
                contradicting.append(link)
        for s in entry.get("key_signals", []):
            if signals.get(s) is False:  # an expected key signal is absent
                contradicting.append(SignalLink(signal=s, present=False, ratio=ratio(cause, s, False)))
        supporting.sort(key=lambda link: -link.ratio)
        contradicting.sort(key=lambda link: link.ratio)

        confirming = entry.get("confirming_signals", [])
        seen = [s for s in confirming if signals.get(s)]
        missing = [s for s in confirming if not signals.get(s)]
        if confirming and not missing and conf >= threshold:
            status = "likely"
        elif conf >= threshold:
            status = "probable"
        else:
            status = "unsupported"

        neighbours = [post[order[j]] for j in (i - 1, i + 1) if 0 <= j < len(order)]
        near_tie = any(abs(conf - n) <= margin for n in neighbours)

        ranked.append(RankedCause(
            rank=i + 1, cause=cause, failure_class=entry.get("class", "unknown"), confidence=round(conf, 6),
            status=status, near_tie=near_tie, supporting=supporting, contradicting=contradicting,
            confirming_seen=seen, confirming_missing=missing, first_check=entry.get("first_check"),
            escalate=bool(entry.get("requires_escalation")), missing_info=missing_info,
        ))
    return ranked


def split_ids(name: str) -> list[str]:
    """Case ids of a split: 'train', 'validation' or 'test' (files in data/eval/uc4/splits/)."""
    path = BACKEND_DIR / "data" / "eval" / "uc4" / "splits" / f"{name}.txt"
    return path.read_text(encoding="utf-8").split()

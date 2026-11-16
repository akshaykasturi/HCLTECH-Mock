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

from app.uc4.models import DistinguishingSignal, EvidenceItem, RankedCause, SignalLink
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

def rank_causes(signals: dict[str, Optional[bool]], evidence: list[EvidenceItem],
                threshold: Optional[float] = None, margin: Optional[float] = None) -> list[RankedCause]:
    """All causes, most likely first, each with supporting/contradicting signals and a status.
    `threshold` and `margin` override settings.yaml (used by scripts/tune_rank.py)."""
    cfg = get_settings()["rank"]
    threshold = cfg["confidence_threshold"] if threshold is None else threshold
    margin = cfg["near_tie_margin"] if margin is None else margin
    min_ratio = cfg["min_ratio"]
    catalog = load_catalog()
    post = posteriors(signals)
    order = sorted(post, key=lambda c: (-post[c], c))
    missing_info = [item.text.removeprefix("Missing: ") for item in evidence if item.kind == "missing"]
    on_signals = [s for s, v in signals.items() if v]

    # Near-tie group: every cause within `margin` of the top one. Only a tie if 2+ causes are in it.
    top_conf = post[order[0]]
    tied = [c for c in order if top_conf - post[c] <= margin]
    tied = set(tied) if len(tied) > 1 else set()

    ranked = []
    for i, cause in enumerate(order):
        entry = catalog.get(cause, {})
        conf = post[cause]
        near_tie = cause in tied

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
        # likely:      all confirming signals seen, confident, and no near-tie with another cause;
        # probable:    confident, OR the top cause, OR tied with the top (the gate recommends these);
        # unsupported: everything else. Never "confirmed": only a human confirms, after first_check.
        if confirming and not missing and conf >= threshold and not near_tie:
            status = "likely"
        elif conf >= threshold or i == 0 or near_tie:
            status = "probable"
        else:
            status = "unsupported"

        ranked.append(RankedCause(
            rank=i + 1, cause=cause, failure_class=entry.get("class", "unknown"), confidence=round(conf, 6),
            status=status, near_tie=near_tie, supporting=supporting, contradicting=contradicting,
            confirming_seen=seen, confirming_missing=missing, first_check=entry.get("first_check"),
            escalate=bool(entry.get("requires_escalation")), missing_info=missing_info,
        ))
    return ranked


def distinguishing_signals(causes: list[str], signals: dict[str, Optional[bool]],
                           min_spread: float, limit: int) -> list[DistinguishingSignal]:
    """Signals whose P(on | cause) differs most between the given causes (spread = max - min >= min_spread).

    These are what to look at to tell the causes apart. Missing-data signals are left out: they
    say nothing about which cause it is.
    """
    likelihoods = load_likelihoods()
    skip = set(get_settings()["rank"]["missing_data_signals"])
    rows = []
    for s in sorted(likelihoods[causes[0]]):
        if s in skip:
            continue
        p_on = {c: likelihoods[c][s] for c in causes}
        spread = max(p_on.values()) - min(p_on.values())
        if spread >= min_spread:
            favours = max(causes, key=lambda c: (p_on[c], -causes.index(c)))
            rows.append((spread, s, DistinguishingSignal(signal=s, favours=favours, p_on=p_on,
                                                         observed=signals.get(s))))
    rows.sort(key=lambda r: (-r[0], r[1]))
    return [r[2] for r in rows[:limit]]


def split_ids(name: str) -> list[str]:
    """Case ids of a split: 'train', 'validation' or 'test' (files in data/eval/uc4/splits/)."""
    path = BACKEND_DIR / "data" / "eval" / "uc4" / "splits" / f"{name}.txt"
    return path.read_text(encoding="utf-8").split()

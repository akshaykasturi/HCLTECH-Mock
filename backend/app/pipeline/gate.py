"""Step 4: deterministic checks that run BEFORE any LLM call.
Returns a list of reason codes. Any ESCALATE/CLARIFY reason stops the pipeline before generation."""
import re
from functools import lru_cache

from app.pipeline.embed import embedder_name
from app.pipeline.retrieve import tokenize

STOP_REASONS = {"SAFETY_KEYWORD": "ESCALATE", "INJECTION_SUSPECTED": "ESCALATE",
                "LOW_RETRIEVAL_SCORE": "ESCALATE", "TOO_VAGUE": "CLARIFY"}


def retrieval_threshold(policy: dict, embedder: str | None = None) -> float:
    """Cosine values are only comparable within one embedding model, so policy.yaml holds one
    threshold per embedder. A missing entry is a configuration error, never a silent default."""
    name = embedder or embedder_name()
    table = policy["gate"]["min_retrieval_strength"]
    if name not in table:
        raise KeyError(f"policy.yaml gate.min_retrieval_strength has no threshold for embedder {name!r}. "
                       f"Run scripts/tune_gate.py with this embedder and add it. Known: {sorted(table)}")
    return float(table[name])


@lru_cache
def _keyword_regex(keywords: tuple[str, ...]) -> re.Pattern:
    """One regex for all keywords, whole words only: \bfire\b matches "fire" but not "firewall".
    Inside a multi-word keyword, any run of whitespace counts as the space."""
    parts = [r"\s+".join(map(re.escape, k.lower().split())) for k in keywords]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b")


@lru_cache
def _injection_regexes(patterns: tuple[str, ...]) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(p) for p in patterns)


def safety_hit(text: str, policy: dict) -> bool:
    """Physical hazard or security incident. Used by the gate and by the P1 override in the orchestrator."""
    return bool(_keyword_regex(tuple(policy["safety_keywords"])).search(text.lower()))


def injection_hit(text: str, policy: dict) -> bool:
    lower = text.lower()
    return any(p.search(lower) for p in _injection_regexes(tuple(policy["injection_patterns"])))


def specific_words(text: str, policy: dict) -> set[str]:
    """Unique meaningful words, minus generic ones ("computer", "issue", "weird") that say nothing
    about what is actually wrong."""
    return set(tokenize(text)) - set(policy["gate"]["generic_words"])


def check(text: str, retrieval_strength: float, policy: dict) -> list[str]:
    reasons = []
    if safety_hit(text, policy):
        reasons.append("SAFETY_KEYWORD")
    if injection_hit(text, policy):
        reasons.append("INJECTION_SUSPECTED")
    if len(specific_words(text, policy)) < policy["gate"]["min_words_for_analysis"]:
        reasons.append("TOO_VAGUE")
    elif retrieval_strength < retrieval_threshold(policy):
        reasons.append("LOW_RETRIEVAL_SCORE")
    return reasons


def stop_outcome(reasons: list[str]) -> str | None:
    """ESCALATE beats CLARIFY. None means the ticket may go to generation."""
    outcomes = {STOP_REASONS[r] for r in reasons if r in STOP_REASONS}
    if "ESCALATE" in outcomes:
        return "ESCALATE"
    if "CLARIFY" in outcomes:
        return "CLARIFY"
    return None

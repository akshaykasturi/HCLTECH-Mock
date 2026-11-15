"""Step 6: check every citation against its source, then decide the final outcome."""
import re

from app.contracts import Citation, Match, Recommendation


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_citations(rec: Recommendation, matches: list[Match]) -> tuple[Recommendation, int]:
    """Keep only citations whose excerpt appears word for word in a source that was actually retrieved.
    Returns the cleaned recommendation and how many citations were dropped."""
    sources = {m.source_id: normalise(m.text) for m in matches}
    kept: list[Citation] = []
    for c in rec.citations:
        excerpt = normalise(c.excerpt)
        if c.source_id in sources and excerpt and excerpt in sources[c.source_id]:
            kept.append(c)
    return rec.model_copy(update={"citations": kept}), len(rec.citations) - len(kept)


def route(classifier_conf: float, retrieval_strength: float, grounding: float,
          n_citations: int, policy: dict) -> tuple[str, list[str], float]:
    """Outcome + reasons + overall confidence (the weakest signal)."""
    reasons = []
    confidence = round(min(classifier_conf, retrieval_strength, grounding), 3)
    if n_citations < policy["route"]["min_citations"]:
        reasons.append("NO_VERIFIED_CITATION")
        return "ESCALATE", reasons, confidence
    if classifier_conf < policy["route"]["min_classifier_confidence"]:
        reasons.append("LOW_CLASSIFIER_CONFIDENCE")
        return "CLARIFY", reasons, confidence
    return "RECOMMEND", reasons, confidence

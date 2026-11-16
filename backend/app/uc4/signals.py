"""Where the yes/no signals for a case come from.

Today: the precomputed derived/observations.jsonl. Later: Raswanth's live signals.
To swap, change get_signals() only; everything else calls it.
"""
import json
from functools import lru_cache

from app.uc4.models import Case
from app.uc4.settings import BACKEND_DIR

OBSERVATIONS = BACKEND_DIR / "data" / "eval" / "uc4" / "derived" / "observations.jsonl"


@lru_cache(maxsize=1)
def _observations() -> dict[str, dict[str, bool]]:
    # Each row also stores labels (expected_cause...). We keep ONLY the "observations" field.
    out = {}
    with open(OBSERVATIONS, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                out[row["case_id"]] = dict(row["observations"])
    return out


def get_signals(case: Case) -> dict[str, bool]:
    """Yes/no signals for one case, e.g. {"status_401": True, "token_age_over_ttl": True, ...}."""
    signals = _observations().get(case.case_id)
    if signals is None:
        raise KeyError(f"no signals for {case.case_id}")
    return dict(signals)

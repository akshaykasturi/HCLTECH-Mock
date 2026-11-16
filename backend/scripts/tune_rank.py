"""Tune confidence_threshold and near_tie_margin on the VALIDATION split only, and write them to settings.yaml.

Threshold: each validation case scores
    labelled case:      RECOMMEND with the right top-1 = +1, RECOMMEND with a wrong top-1 = -1, CLARIFY = 0
    insufficient case:  CLARIFY = +1, RECOMMEND = -1
  Every threshold in the best-scoring range is equally good on validation; we take the middle of that range,
  so a small shift in the data does not flip decisions.
Margin: a near-tie flag should warn about a wrong top-1. For labelled cases, score +1 when the flag is right
  (flag on a wrong top-1, no flag on a right top-1), and take the middle of the best range.

Usage (from backend):  .\\.venv\\Scripts\\python.exe scripts\\tune_rank.py   (add --dry-run to not write)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.uc4.diagnose import diagnose  # noqa: E402
from app.uc4.gate import decide  # noqa: E402
from app.uc4.rank import split_ids  # noqa: E402
from app.uc4.settings import SETTINGS_FILE  # noqa: E402
from app.uc4.store import get_case  # noqa: E402

THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 20)]  # 0.05 .. 0.95
MARGINS = [round(0.05 * i, 2) for i in range(0, 11)]  # 0.00 .. 0.50


def _middle_of_best(grid: list[float], scores: list[float]) -> tuple[float, float, float, float]:
    """(chosen value, best score, low end, high end) of the longest run of best-scoring values."""
    best = max(scores)
    runs, run = [], []
    for value, score in zip(grid, scores):
        if score == best:
            run.append(value)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    longest = max(runs, key=len)
    return round((longest[0] + longest[-1]) / 2, 3), best, longest[0], longest[-1]


def main(argv: list[str]) -> int:
    diags = [diagnose(get_case(cid)) for cid in split_ids("validation")]
    labelled = [d for d in diags if d.case.expected_cause]
    print(f"validation: {len(diags)} cases ({len(labelled)} labelled, {len(diags) - len(labelled)} insufficient)")

    def threshold_score(t: float) -> int:
        score = 0
        for d in diags:
            outcome = decide(d.ranked, d.signals, d.evidence, threshold=t).outcome
            if d.case.expected_cause is None:
                score += 1 if outcome == "CLARIFY" else -1
            elif outcome == "RECOMMEND":
                score += 1 if d.ranked[0].cause == d.case.expected_cause else -1
        return score

    def margin_score(m: float) -> int:
        score = 0
        for d in labelled:
            gap = d.ranked[0].confidence - d.ranked[1].confidence
            flagged = gap <= m
            wrong = d.ranked[0].cause != d.case.expected_cause
            score += 1 if flagged == wrong else 0
        return score

    t_scores = [threshold_score(t) for t in THRESHOLDS]
    m_scores = [margin_score(m) for m in MARGINS]
    threshold, t_best, t_lo, t_hi = _middle_of_best(THRESHOLDS, t_scores)
    margin, m_best, m_lo, m_hi = _middle_of_best(MARGINS, m_scores)

    print("threshold score: " + "  ".join(f"{t:.2f}:{s}" for t, s in zip(THRESHOLDS, t_scores)))
    print(f"-> confidence_threshold {threshold} (score {t_best}, best range {t_lo}-{t_hi})")
    print("margin score:    " + "  ".join(f"{m:.2f}:{s}" for m, s in zip(MARGINS, m_scores)))
    print(f"-> near_tie_margin {margin} (score {m_best}/{len(labelled)}, best range {m_lo}-{m_hi})")
    print("top-1 gaps on validation (wrong top-1 marked *): " + ", ".join(
        f"{d.case.case_id}{'*' if d.ranked[0].cause != d.case.expected_cause else ''}="
        f"{d.ranked[0].confidence - d.ranked[1].confidence:.2f}" for d in labelled))

    if "--dry-run" in argv:
        return 0
    text = SETTINGS_FILE.read_text(encoding="utf-8")
    text, n1 = re.subn(r"(?m)^(  confidence_threshold:) .*$", rf"\g<1> {threshold}", text)
    text, n2 = re.subn(r"(?m)^(  near_tie_margin:) .*$", rf"\g<1> {margin}", text)
    if (n1, n2) != (1, 1):
        print("could not find the two lines to update in settings.yaml")
        return 1
    SETTINGS_FILE.write_text(text, encoding="utf-8")
    print(f"wrote {SETTINGS_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

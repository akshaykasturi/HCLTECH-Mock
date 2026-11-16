"""Tune confidence_threshold and near_tie_margin on the VALIDATION split only, and write them to settings.yaml.

CLARIFY no longer depends on these numbers (only missing evidence gives CLARIFY). They decide when a
RECOMMEND comes with alternatives ("not a clear winner, here is how to tell them apart").
Each labelled validation case scores:
    right top-1, no alternatives shown            +1  (clean answer)
    right top-1, alternatives shown                0  (harmless, but noise)
    wrong top-1, true cause among alternatives    +1  (we warned, and pointed at the right one)
    wrong top-1, true cause not shown             -1  (confidently wrong)
Threshold first (margin 0), then margin with that threshold. Every value in the best-scoring range is
equally good on validation; we take the middle of the range so a small data shift does not flip decisions.
Insufficient cases are decided by the missing-evidence rules alone; they are only checked here.

Usage (from backend):  .\\.venv\\Scripts\\python.exe scripts\\tune_rank.py   (add --dry-run to not write)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.uc4.diagnose import diagnose  # noqa: E402
from app.uc4.gate import decide  # noqa: E402
from app.uc4.rank import rank_causes, split_ids  # noqa: E402
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
    insufficient = [d for d in diags if not d.case.expected_cause]
    print(f"validation: {len(diags)} cases ({len(labelled)} labelled, {len(insufficient)} insufficient)")
    for d in insufficient:
        print(f"  insufficient {d.case.case_id}: {d.decision.outcome} ({'; '.join(d.decision.reasons)})")

    def score(t: float, m: float) -> int:
        total = 0
        for d in labelled:
            ranked = rank_causes(d.signals, d.evidence, threshold=t, margin=m)
            decision = decide(ranked, d.signals, d.evidence, threshold=t)
            if decision.outcome == "CLARIFY":  # labelled cases never have missing evidence; just in case
                continue
            right = ranked[0].cause == d.case.expected_cause
            if right:
                total += 0 if decision.alternatives else 1
            else:
                total += 1 if d.case.expected_cause in decision.alternatives else -1
        return total

    t_scores = [score(t, 0.0) for t in THRESHOLDS]
    threshold, t_best, t_lo, t_hi = _middle_of_best(THRESHOLDS, t_scores)
    m_scores = [score(threshold, m) for m in MARGINS]
    margin, m_best, m_lo, m_hi = _middle_of_best(MARGINS, m_scores)

    print("threshold score (margin 0): " + "  ".join(f"{t:.2f}:{s}" for t, s in zip(THRESHOLDS, t_scores)))
    print(f"-> confidence_threshold {threshold} (score {t_best}/{len(labelled)}, best range {t_lo}-{t_hi})")
    print(f"margin score (threshold {threshold}): " + "  ".join(f"{m:.2f}:{s}" for m, s in zip(MARGINS, m_scores)))
    print(f"-> near_tie_margin {margin} (score {m_best}/{len(labelled)}, best range {m_lo}-{m_hi})")
    print("top-1 confidence / gap on validation (wrong top-1 marked *): " + ", ".join(
        f"{d.case.case_id}{'*' if d.ranked[0].cause != d.case.expected_cause else ''}="
        f"{d.ranked[0].confidence:.2f}/{d.ranked[0].confidence - d.ranked[1].confidence:.2f}" for d in labelled))

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

"""Evaluate ranking + CLARIFY gate on the TEST split, with bootstrap 95% confidence intervals.

Ranking metrics (top-1, top-3, MRR, class accuracy) use the labelled test cases, whatever the gate says,
so they compare directly with the naive-Bayes baseline in derived/baseline_report.md.
Gate metrics: CLARIFY rate on the insufficient cases (higher is better) and false CLARIFY rate on the
labelled cases (lower is better).

Usage (from backend):  .\\.venv\\Scripts\\python.exe scripts\\eval_rank.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.stats import bootstrap_ci  # noqa: E402
from app.uc4.diagnose import diagnose  # noqa: E402
from app.uc4.rank import split_ids  # noqa: E402
from app.uc4.settings import BACKEND_DIR, get_settings  # noqa: E402
from app.uc4.store import get_case  # noqa: E402

BASELINE = BACKEND_DIR / "data" / "eval" / "uc4" / "derived" / "baseline_report.md"


def baseline_row(likelihoods: str = "learned", split: str = "test") -> dict[str, str]:
    """Read one row of the naive-Bayes baseline table from baseline_report.md."""
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] == likelihoods and cells[1] == split:
            return {"n": cells[2], "top1": cells[3], "top3": cells[4], "mrr": cells[5], "class_acc": cells[6]}
    return {}


def _fmt(values: list[float]) -> str:
    if not values:
        return "n/a"
    point, low, high = bootstrap_ci(values)
    return f"{point:.2f} [{low:.2f}, {high:.2f}]"


def main() -> int:
    diags = [diagnose(get_case(cid)) for cid in split_ids("test")]
    labelled = [d for d in diags if d.case.expected_cause]
    insufficient = [d for d in diags if not d.case.expected_cause]

    top1, top3, rr, class_ok, false_clarify = [], [], [], [], []
    for d in labelled:
        order = [r.cause for r in d.ranked]
        pos = order.index(d.case.expected_cause) + 1
        top1.append(float(pos == 1))
        top3.append(float(pos <= 3))
        rr.append(1.0 / pos)
        class_ok.append(float(d.ranked[0].failure_class == d.case.expected_class))
        false_clarify.append(float(d.decision.outcome == "CLARIFY"))
    clarify = [float(d.decision.outcome == "CLARIFY") for d in insufficient]
    answered = [float(d.ranked[0].cause == d.case.expected_cause) for d in labelled if d.decision.outcome == "RECOMMEND"]
    likely_right = [float(d.ranked[0].cause == d.case.expected_cause) for d in labelled if d.ranked[0].status == "likely"]

    base = baseline_row()
    cfg = get_settings()["rank"]
    print(f"Test split: {len(diags)} cases ({len(labelled)} labelled, {len(insufficient)} insufficient). "
          f"threshold {cfg['confidence_threshold']}, margin {cfg['near_tie_margin']} (tuned on validation).")
    print("Values: mean [bootstrap 95% CI].\n")
    rows = [
        ("Top-1 cause", _fmt(top1), base.get("top1", "n/a")),
        ("Top-3 cause", _fmt(top3), base.get("top3", "n/a")),
        ("MRR", _fmt(rr), base.get("mrr", "n/a")),
        ("Class accuracy", _fmt(class_ok), base.get("class_acc", "n/a")),
        (f"CLARIFY rate, insufficient (n={len(clarify)})", _fmt(clarify), "-"),
        (f"False CLARIFY rate, labelled (n={len(false_clarify)})", _fmt(false_clarify), "-"),
        (f"Top-1 when RECOMMEND (n={len(answered)})", _fmt(answered), "-"),
        (f"Top-1 when status likely (n={len(likely_right)})", _fmt(likely_right), "-"),
    ]
    width = max(len(r[0]) for r in rows)
    print(f"| {'Metric':<{width}} | {'rank.py (this)':<20} | Baseline NB (learned, test) |")
    print(f"|{'-' * (width + 2)}|{'-' * 22}|{'-' * 29}|")
    for name, ours, theirs in rows:
        print(f"| {name:<{width}} | {ours:<20} | {theirs:<27} |")

    wrong = [f"{d.case.case_id}: {d.case.expected_cause} -> {d.ranked[0].cause} ({d.ranked[0].confidence:.2f}, "
             f"{d.decision.outcome})" for d in labelled if d.ranked[0].cause != d.case.expected_cause]
    clarified = [f"{d.case.case_id} ({d.ranked[0].confidence:.2f})" for d in labelled if d.decision.outcome == "CLARIFY"]
    print("\nWrong top-1: " + ("; ".join(wrong) or "none"))
    print("Labelled cases sent to CLARIFY: " + (", ".join(clarified) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

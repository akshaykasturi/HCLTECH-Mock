"""Pick the retrieval-strength threshold for the gate WITHOUT looking at the test set.

Usage (from backend/):  python scripts/tune_gate.py
          offline test threshold:  $env:EMBEDDER="hash"; python scripts/tune_gate.py

Uses data/validation/validation_tickets.csv only: 20 in-scope tickets in natural wording and 15
out-of-scope ones (facilities, HR...). These tickets are for tuning, never for reporting results.

For each threshold it shows the share of in-scope tickets that would be wrongly escalated and the
share of out-of-scope tickets that would wrongly pass, and recommends the threshold with the best
balanced accuracy (the average of the two success rates, so the smaller group counts as much as the
larger). When several thresholds tie, the middle of that range is chosen: it is furthest from both edges.
The threshold goes into app/policy.yaml under gate.min_retrieval_strength, keyed by embedder name,
because cosine values from different models are not comparable.
"""
import csv
import statistics
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import get_policy, get_settings  # noqa: E402
from app.pipeline import gate  # noqa: E402
from app.pipeline.redact import redact  # noqa: E402
from app.pipeline.retrieve import Index, get_index  # noqa: E402

GRID = [round(x / 100, 2) for x in range(30, 96)]  # 0.30 .. 0.95


def measure(index: Index | None = None) -> list[dict]:
    """Retrieval strength of every validation ticket, plus which other gate rules would stop it anyway."""
    index = index or get_index()
    policy = get_policy()
    path = get_settings().data_dir / "validation" / "validation_tickets.csv"
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        text = redact(r["description"])[0]
        hits = index.search(text, top_k=1)
        strength = hits[0][1] if hits else 0.0
        # every gate rule except the one being tuned: strength 1.0 can never trigger LOW_RETRIEVAL_SCORE
        other = [x for x in gate.check(text, 1.0, policy) if x != "LOW_RETRIEVAL_SCORE"]
        out.append(dict(val_id=r["val_id"], in_scope=r["expected"] == "in_scope", strength=strength,
                        other_reasons=other, best=hits[0][0].source_id if hits else "",
                        text=r["description"]))
    return out


def distribution(rows: list[dict]) -> dict[str, tuple[float, float, float, int]]:
    """(min, median, max, count) of strength for in-scope and out-of-scope tickets."""
    out = {}
    for label, want in (("in_scope", True), ("out_of_scope", False)):
        s = [r["strength"] for r in rows if r["in_scope"] == want]
        out[label] = (round(min(s), 3), round(statistics.median(s), 3), round(max(s), 3), len(s))
    return out


def sweep(rows: list[dict]) -> list[dict]:
    ins = [r["strength"] for r in rows if r["in_scope"]]
    outs = [r["strength"] for r in rows if not r["in_scope"]]
    table = []
    for t in GRID:
        wrongly_escalated = sum(s < t for s in ins) / len(ins)
        wrongly_passed = sum(s >= t for s in outs) / len(outs)
        table.append(dict(threshold=t, wrongly_escalated=wrongly_escalated, wrongly_passed=wrongly_passed,
                          balanced_acc=round(1 - (wrongly_escalated + wrongly_passed) / 2, 4)))
    return table


def recommend(table: list[dict]) -> float:
    best = max(r["balanced_acc"] for r in table)
    tied = [r["threshold"] for r in table if r["balanced_acc"] == best]
    return tied[len(tied) // 2]


def main() -> None:
    index = get_index()
    rows = measure(index)
    dist = distribution(rows)
    table = sweep(rows)
    best = recommend(table)

    print(f"Embedder: {index.embedder.name}   validation tickets: {len(rows)}\n")
    print("Strength distribution (cosine to the best match):")
    print("  group          n    min   median   max")
    for label, (lo, med, hi, n) in dist.items():
        print(f"  {label:<13} {n:>2}  {lo:.3f}  {med:.3f}   {hi:.3f}")
    gap = dist["in_scope"][0] - dist["out_of_scope"][2]
    print(f"  {'separated' if gap > 0 else 'OVERLAP'}: lowest in-scope minus highest out-of-scope = {gap:+.3f}\n")

    lo = min(r["strength"] for r in rows) - 0.02
    hi = max(r["strength"] for r in rows) + 0.02
    print("threshold  in-scope wrongly escalated  out-of-scope wrongly passed  balanced acc")
    for r in table:
        if lo <= r["threshold"] <= hi or r["threshold"] == best:
            mark = "  <- recommended" if r["threshold"] == best else ""
            print(f"  {r['threshold']:.2f}     {r['wrongly_escalated']:>6.1%}                    "
                  f"{r['wrongly_passed']:>6.1%}                    {r['balanced_acc']:.3f}{mark}")

    print(f"\nAt {best:.2f}, these validation tickets are on the wrong side:")
    wrong = [r for r in rows if (r["strength"] < best) == r["in_scope"]]
    for r in wrong or []:
        side = "in-scope, escalated" if r["in_scope"] else "out-of-scope, passed"
        caught = f" (also caught by: {', '.join(r['other_reasons'])})" if r["other_reasons"] else ""
        print(f"  {r['val_id']}  {r['strength']:.3f}  {side}{caught}  {r['text'][:70]}")
    if not wrong:
        print("  none")

    print(f"\nRecommended gate.min_retrieval_strength for {index.embedder.name!r} = {best:.2f}  (set it in app/policy.yaml)")
    current = get_policy()["gate"]["min_retrieval_strength"].get(index.embedder.name)
    print(f"Current value in policy.yaml: {current}")


if __name__ == "__main__":
    main()

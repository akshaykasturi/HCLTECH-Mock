"""Evaluate doc search on data/eval/uc4/retrieval_gold.jsonl: BM25 vs dense vs hybrid.

The gold labels are DOCUMENTS (gold_doc_ids), so a hit counts when its section belongs to a gold document.
  recall@k:  share of answerable questions with a gold document in the top k sections
  MRR:       mean of 1 / rank of the first gold section (0 if none in the top 10)
No-answer questions (gold_doc_ids empty): we report the top score each method still gives them, next to
the median top score on answerable questions; a big gap would let a threshold say "the docs don't cover this".
Deprecated check: legacy/rate-limits-v1 must never appear by default (gold questions and all 90 case queries).

Usage (from backend):  .\\.venv\\Scripts\\python.exe scripts\\eval_doc_search.py
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.stats import bootstrap_ci  # noqa: E402
from app.uc4.doc_search import get_index, search  # noqa: E402
from app.uc4.evidence import doc_queries  # noqa: E402
from app.uc4.store import load_cases, logs_by_correlation_id  # noqa: E402

GOLD = Path(__file__).resolve().parents[1] / "data" / "eval" / "uc4" / "retrieval_gold.jsonl"
METHODS = ("bm25", "dense", "hybrid")
DEPRECATED = "legacy/rate-limits-v1"


def _ci(values: list[float]) -> str:
    point, low, high = bootstrap_ci(values)
    return f"{point:.2f} [{low:.2f}, {high:.2f}]"


def main() -> int:
    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    answerable = [r for r in rows if r["gold_doc_ids"]]
    no_answer = [r for r in rows if not r["gold_doc_ids"]]
    if get_index().mode != "hybrid":
        print("Embeddings are not available (offline or UC4_DOC_SEARCH_DENSE=0): only BM25 can be evaluated.")
        return 1
    print(f"Retrieval gold: {len(rows)} questions ({len(answerable)} answerable, {len(no_answer)} no-answer); "
          f"{len(get_index().sections)} sections indexed. Values: mean [bootstrap 95% CI].\n")

    results = {}
    for m in METHODS:
        r3, r5, rr = [], [], []
        for q in answerable:
            hits = search(q["query"], k=10, method=m)
            ranks = [h.rank for h in hits if h.doc_id in q["gold_doc_ids"]]
            first = ranks[0] if ranks else None
            r3.append(float(first is not None and first <= 3))
            r5.append(float(first is not None and first <= 5))
            rr.append(1.0 / first if first else 0.0)
        results[m] = (r3, r5, rr)

    print("| Method | recall@3 | recall@5 | MRR |")
    print("|---|---|---|---|")
    for m in METHODS:
        r3, r5, rr = results[m]
        print(f"| {m} | {_ci(r3)} | {_ci(r5)} | {_ci(rr)} |")

    print("\nNo-answer questions: top score each method still returns (vs median top score on answerable)")
    print("| Question | BM25 top | dense top (cosine) | hybrid top hit |")
    print("|---|---|---|---|")
    for q in no_answer:
        b = search(q["query"], k=1, method="bm25")[0]
        d = search(q["query"], k=1, method="dense")[0]
        h = search(q["query"], k=1, method="hybrid")[0]
        print(f"| {q['query']} | {b.bm25_score:.2f} | {d.dense_score:.3f} | {h.section_id} |")
    med_b = statistics.median(search(q["query"], k=1, method="bm25")[0].bm25_score for q in answerable)
    med_d = statistics.median(search(q["query"], k=1, method="dense")[0].dense_score for q in answerable)
    print(f"| (median top on answerable) | {med_b:.2f} | {med_d:.3f} | |")

    queries = [q["query"] for q in rows]
    for case in load_cases().values():
        focal = logs_by_correlation_id(case.focal_correlation_id)
        if focal:
            queries.extend(doc_queries(focal[0], case.route))
    leaks = sum(1 for q in queries for m in METHODS for h in search(q, k=10, method=m) if h.doc_id == DEPRECATED)
    shown_when_asked = any(h.doc_id == DEPRECATED
                           for h in search("rate limit requests per minute", k=5, include_deprecated=True))
    print(f"\nDeprecated {DEPRECATED}: appears {leaks} times in the top 10 of {len(queries)} queries x "
          f"{len(METHODS)} methods by default (must be 0); "
          f"{'found' if shown_when_asked else 'not found'} when include_deprecated=True.")
    return 0 if leaks == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

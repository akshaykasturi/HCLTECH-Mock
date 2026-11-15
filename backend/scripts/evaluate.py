"""Evaluate the assistant on the test sets and write docs/eval_report.md.

Usage (from backend/):  python scripts/evaluate.py

What is measured, separately for each test source (generator holdout, hand-written, novel...):
  Classification  accuracy and macro-F1 for subcategory, category, priority; calibration error (ECE)
                  for the new model vs the kNN baseline.
  Retrieval       for BM25 only, dense only and hybrid (RRF of both, what the app uses):
                  recall@5  - is at least one truly similar ticket (same scenario) in the top 5?
                  MRR       - 1 / rank of the first truly similar result (1.0 = always first)
                  lookalike rate - how often a hard-negative (lookalike) result beats the first correct one
  Routing         outcome accuracy: RECOMMEND / CLARIFY / ESCALATE vs the expected outcome
Also shown: the gate's strength distribution on the validation set (tuning data, not a result).
Everything here runs offline (extractive generator, no LLM calls). The embedder is EMBEDDER/EMBED_MODEL.
"""
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score  # noqa: E402
from tune_gate import distribution, measure  # noqa: E402

from app.config import get_policy, get_settings  # noqa: E402
from app.contracts import TicketIn  # noqa: E402
from app.pipeline.classify import classify, knn_vote  # noqa: E402
from app.pipeline.gate import retrieval_threshold  # noqa: E402
from app.pipeline.orchestrator import analyse  # noqa: E402
from app.pipeline.redact import redact  # noqa: E402
from app.pipeline.retrieve import MODES, get_index  # noqa: E402

K = 5


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("test_id")]


def load_test_set(data: Path) -> list[dict]:
    """Join test tickets with their labels. Hand-written tickets carry their labels in the same file."""
    labels = {r["test_id"]: r for r in read_csv(data / "test" / "labels.csv")}
    cases = []
    for name in ("holdout_tickets.csv", "novel_tickets.csv", "paraphrased_tickets.csv"):
        for t in read_csv(data / "test" / name):
            if t["test_id"] in labels:
                cases.append({**labels[t["test_id"]], **t})
    for t in read_csv(data / "test" / "handwritten_tickets.csv"):
        cases.append({**t, "source": "handwritten", "hard_negative_scenario": t.get("hard_negative_scenario", "")})
    return cases


def scenario_lookup(data: Path) -> dict[str, str]:
    """source_id -> scenario_id, for scoring retrieval. The app itself never sees this."""
    ids = {r["ticket_id"]: r["scenario_id"] for r in read_csv_any(data / "historical_tickets.csv")}
    for a in json.loads((data / "kb_articles.json").read_text(encoding="utf-8")):
        ids[a["kb_id"]] = a["scenario_id"]
    return ids


def read_csv_any(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ece(confidences: list[float], correct: list[bool], bins: int = 10) -> float:
    """Expected calibration error: average gap between stated confidence and actual accuracy."""
    total, err = len(confidences), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if lo < c <= hi or (b == 0 and c == 0)]
        if idx:
            acc = sum(correct[i] for i in idx) / len(idx)
            conf = sum(confidences[i] for i in idx) / len(idx)
            err += len(idx) / total * abs(acc - conf)
    return round(err, 3)


def classification_block(cases: list[dict]) -> dict:
    out = {}
    for name, fn in (("calibrated_logreg", classify), ("knn_vote", knn_vote)):
        preds = [fn(redact(f"{c['title']}. {c['description']}")[0]) for c in cases]
        sub_true = [c["subcategory"] for c in cases]
        sub_pred = [p.subcategory for p in preds]
        correct = [a == b for a, b in zip(sub_true, sub_pred)]
        out[name] = dict(
            subcategory_acc=round(accuracy_score(sub_true, sub_pred), 3),
            subcategory_macro_f1=round(f1_score(sub_true, sub_pred, average="macro", zero_division=0), 3),
            category_acc=round(accuracy_score([c["category"] for c in cases], [p.category for p in preds]), 3),
            priority_acc=round(accuracy_score([c["priority"] for c in cases], [p.priority for p in preds]), 3),
            ece=ece([p.confidence for p in preds], correct),
            mean_confidence=round(sum(p.confidence for p in preds) / len(preds), 3),
        )
        if name == "calibrated_logreg":
            out["_category_pairs"] = list(zip([c["category"] for c in cases], [p.category for p in preds]))
    return out


def retrieval_block(cases: list[dict], scen: dict[str, str], mode: str) -> dict:
    index, recall, rr, lookalike_wins = get_index(), [], [], 0
    for c in cases:
        hits = index.rank(redact(f"{c['title']}. {c['description']}")[0], top_k=K, mode=mode)
        ranked = [scen.get(m.source_id, "") for m, _ in hits]
        first = next((i for i, s in enumerate(ranked) if s == c["scenario_id"]), None)
        recall.append(first is not None)
        rr.append(1 / (first + 1) if first is not None else 0.0)
        bad = c.get("hard_negative_scenario")
        first_bad = next((i for i, s in enumerate(ranked) if bad and s == bad), None)
        if first_bad is not None and (first is None or first_bad < first):
            lookalike_wins += 1
    n = len(cases)
    return dict(recall_at_5=round(sum(recall) / n, 3), mrr=round(sum(rr) / n, 3),
                lookalike_beats_correct=round(lookalike_wins / n, 3))


def outcome_block(cases: list[dict]) -> dict:
    rows, latencies = [], []
    for c in cases:
        start = time.perf_counter()
        r = analyse(TicketIn(title=c["title"][:200] or "ticket", description=c["description"]), None)
        latencies.append((time.perf_counter() - start) * 1000)
        rows.append(dict(test_id=c["test_id"], expected=c["expected_outcome"], got=r.outcome,
                         reasons=",".join(r.reasons), text=c["description"][:70],
                         seen=c.get("seen_by_rules", "").strip().lower() == "yes"))
    acc = sum(r["expected"] == r["got"] for r in rows) / len(rows)
    latencies.sort()
    return dict(outcome_acc=round(acc, 3), p50_ms=round(latencies[len(latencies) // 2]),
                p95_ms=round(latencies[int(len(latencies) * 0.95) - 1]), rows=rows)


def confusion_table(pairs: list[tuple[str, str]]) -> str:
    labels = sorted({t for t, _ in pairs})
    m = confusion_matrix([t for t, _ in pairs], [p for _, p in pairs], labels=labels)
    short = [l.split(" ")[0][:8] for l in labels]
    lines = ["| true \\ predicted | " + " | ".join(short) + " |", "|---" * (len(labels) + 1) + "|"]
    for label, row in zip(short, m):
        lines.append(f"| {label} | " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def main() -> None:
    data = get_settings().data_dir
    cases, scen = load_test_set(data), scenario_lookup(data)
    by_source = defaultdict(list)
    for c in cases:
        by_source[c["source"]].append(c)

    index = get_index()
    threshold = retrieval_threshold(get_policy(), index.embedder.name)
    report = ["# Evaluation report", "",
              f"Generated by `scripts/evaluate.py`. Offline run: extractive generator, no LLM calls. "
              f"Embedder: `{index.embedder.name}`. Gate threshold (cosine): {threshold}. "
              f"Test tickets: {len(cases)} ({', '.join(f'{k}: {len(v)}' for k, v in by_source.items())}).", "",
              "Each source is reported **separately**. Generator-holdout tickets come from the same scenarios as the "
              "training data, so their scores are optimistic. Hand-written, paraphrased and novel tickets are the real test.", "",
              "**Who wrote the test data:** the hand-written test tickets (`data/test/handwritten_tickets.csv`) and the "
              "validation tickets (`data/validation/validation_tickets.csv`) were written by the AI assistant that helped "
              "build this project, not by real users. They use natural wording unlike the generator's templates, but they "
              "are not a substitute for real tickets.", ""]
    summary = {}

    for source, group in by_source.items():
        labelled = [c for c in group if c.get("subcategory")]
        report += [f"## Source: {source} ({len(group)} tickets)", ""]
        if labelled:
            cls = classification_block(labelled)
            pairs = cls.pop("_category_pairs")
            report += ["### Classification", "",
                       "| Model | Subcat acc | Subcat macro-F1 | Category acc | Priority acc | ECE (lower = more honest confidence) | Mean confidence |",
                       "|---|---|---|---|---|---|---|"]
            for name, m in cls.items():
                report.append(f"| {name} | {m['subcategory_acc']} | {m['subcategory_macro_f1']} | {m['category_acc']} | "
                              f"{m['priority_acc']} | {m['ece']} | {m['mean_confidence']} |")
            report += ["", "Category confusion matrix (calibrated_logreg):", "", confusion_table(pairs), ""]
            ret = {mode: retrieval_block(labelled, scen, mode) for mode in MODES}
            report += ["### Retrieval", "", "| Method | Recall@5 | MRR | Lookalike ranked above correct |",
                       "|---|---|---|---|"]
            report += [f"| {mode}{' (used by the app)' if mode == 'hybrid' else ''} | {r['recall_at_5']} | {r['mrr']} | "
                       f"{r['lookalike_beats_correct']} |" for mode, r in ret.items()] + [""]
            summary[source] = {"classification": cls, "retrieval": ret}
        if not labelled:  # unknown problem types: a trustworthy classifier should NOT be confident here
            texts = [redact(f"{c['title']}. {c['description']}")[0] for c in group]
            ood = {name: round(sum(fn(t).confidence for t in texts) / len(texts), 3)
                   for name, fn in (("calibrated_logreg", classify), ("knn_vote", knn_vote))}
            report += ["### Classifier confidence on unknown problem types (lower is better)", "",
                       "| Model | Mean confidence |", "|---|---|"]
            report += [f"| {k} | {v} |" for k, v in ood.items()] + [""]
            summary[source] = {"ood_mean_confidence": ood}
        out = outcome_block(group)
        routing = {k: v for k, v in out.items() if k != "rows"}
        seen_rows = [r for r in out["rows"] if r["seen"]]
        if seen_rows:  # some tickets shaped a gate rule: report them apart from the clean number
            unseen_rows = [r for r in out["rows"] if not r["seen"]]
            acc = lambda rs: round(sum(r["expected"] == r["got"] for r in rs) / len(rs), 3)  # noqa: E731
            routing.update(unseen_acc=acc(unseen_rows), unseen_n=len(unseen_rows),
                           seen_acc=acc(seen_rows), seen_n=len(seen_rows))
            report += ["### Routing", "",
                       f"Outcome accuracy, **unseen tickets only: {routing['unseen_acc']}** ({len(unseen_rows)} tickets) "
                       f"· seen tickets (regression check): {routing['seen_acc']} ({len(seen_rows)} tickets) "
                       f"· latency p50 {out['p50_ms']} ms, p95 {out['p95_ms']} ms", "",
                       "Tickets marked *seen* (`seen_by_rules=yes`) were looked at while writing gate rules, so they "
                       "only check those rules still work; the unseen number is the honest measure.", ""]
        else:
            report += ["### Routing", "", f"Outcome accuracy: **{out['outcome_acc']}** · latency p50 {out['p50_ms']} ms, "
                       f"p95 {out['p95_ms']} ms", ""]
        wrong = [r for r in out["rows"] if r["expected"] != r["got"]]
        if source != "generator_holdout" or wrong:
            show = out["rows"] if source != "generator_holdout" else wrong[:15]
            if seen_rows:
                report += ["| Test | Seen by rules | Expected | Got | Reasons | Ticket |", "|---|---|---|---|---|---|"]
                report += [f"| {r['test_id']} | {'yes' if r['seen'] else 'no'} | {r['expected']} | {r['got']} | "
                           f"{r['reasons']} | {r['text']} |" for r in show]
            else:
                report += ["| Test | Expected | Got | Reasons | Ticket |", "|---|---|---|---|---|"]
                report += [f"| {r['test_id']} | {r['expected']} | {r['got']} | {r['reasons']} | {r['text']} |" for r in show]
            report.append("")
        summary.setdefault(source, {})["routing"] = routing

    dist = distribution(measure(index))
    report += ["## Gate threshold: validation set (tuning data, not a result)", "",
               f"Retrieval strength = cosine similarity to the best match. The threshold ({threshold}) was chosen by "
               "`scripts/tune_gate.py` on these tickets (best balanced accuracy). They are never used to report results.", "",
               "| Validation group | n | Min | Median | Max |", "|---|---|---|---|---|"]
    report += [f"| {label} | {n} | {lo} | {med} | {hi} |" for label, (lo, med, hi, n) in dist.items()]
    gap = round(dist["in_scope"][0] - dist["out_of_scope"][2], 3)
    report += ["", f"Lowest in-scope minus highest out-of-scope: {gap:+} "
               f"({'the groups are separated' if gap > 0 else 'the groups overlap: some tickets land on the wrong side of any threshold'}).", ""]
    summary["validation_strength"] = dist

    report += ["## Known limitations", "",
               "- Generator-holdout scores are optimistic: same scenarios and phrase pools as training.",
               "- Calibration makes confidence honest for familiar tickets only. For unseen problem types the classifier can "
               "still be confident and wrong, which is why the retrieval gate and min(signals) exist.",
               f"- The retrieval-strength threshold ({threshold}) was tuned on 35 validation tickets "
               "(`scripts/tune_gate.py`), never on these test tickets. 35 is small, so the threshold is a rough estimate.",
               "- The hand-written and validation tickets were written by the AI assistant, not by real users.",
               "- Priority accuracy on generator tickets is inflated: impact phrases come from a fixed pool per priority.",
               "- Cosine similarity depends on the embedding model: changing EMBED_MODEL needs a newly tuned threshold.", ""]

    docs = BACKEND.parent / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "eval_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nReport written to {docs / 'eval_report.md'}")


if __name__ == "__main__":
    main()

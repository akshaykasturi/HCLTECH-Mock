"""Compare several evaluated models on the same test rows: leaderboard, McNemar tests, per-class F1,
gain over the rules baseline, TF-IDF vs embeddings, a recommendation and warnings.

compare() returns a JSON-ready dict; to_markdown() renders it. McNemar comes from app.analysis.stats.
"""
import itertools
import logging
from typing import Any

import numpy as np

from app.analysis.stats import mcnemar

logger = logging.getLogger(__name__)

ALPHA = 0.05
LEAK_F1 = 0.98
LOW_RECALL = 0.5
BASELINE = "rules"
SIMPLICITY = ["rules", "lr", "linear_svc", "rf"]  # simpler / faster / better-calibrated first
WHY_SIMPLER = {
    "lr": "Logistic Regression is the simplest model (one weight per feature and class), cheap to predict and easy to explain",
    "linear_svc": "LinearSVC is simpler and faster than a 200-500 tree forest",
    "rf": "Random Forest",
}
ECE_NOTE_GAP = 0.05  # mention calibration when the pick's ECE is this much worse than the best-calibrated tied model


def _kind(name: str) -> str:
    """Model type from a name like 'embeddings/lr' -> 'lr'."""
    return name.split("/")[-1]


def _fmt(v: Any, digits: int = 3) -> str:
    """Number with fixed digits, or N/A for None."""
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _ci(r: dict, key: str = "macro_f1") -> tuple[float | None, float | None]:
    """(low, high) bootstrap interval of a metric."""
    b = r["bootstrap_95ci"][key]
    return b["low"], b["high"]


def compare(
    results: dict[str, dict[str, Any]], predictions: dict[str, Any], y_true: Any,
    timings: dict[str, dict[str, float]] | None = None, baseline: str = BASELINE, alpha: float = ALPHA,
) -> dict[str, Any]:
    """Build the comparison of all models evaluated on the same rows (see module docstring)."""
    y = np.asarray(y_true).astype(str)
    timings = timings or {}
    for name, pred in predictions.items():
        if len(pred) != len(y):
            raise ValueError(f"{name}: {len(pred)} predictions for {len(y)} rows; models must share the test rows")
    class_orders = {tuple(r["classes"]) for r in results.values()}
    if len(class_orders) != 1:
        raise ValueError(f"models disagree on class order: {class_orders}")
    classes = list(next(iter(class_orders)))

    names = sorted(results, key=lambda n: -(results[n]["overall"]["macro_f1"] or 0.0))
    leaderboard = []
    for n in names:
        o = results[n]["overall"]
        low, high = _ci(results[n])
        t = timings.get(n, {})
        leaderboard.append({
            "model": n, "macro_f1": o["macro_f1"], "macro_f1_low": low, "macro_f1_high": high,
            "accuracy": o["accuracy"], "balanced_accuracy": o["balanced_accuracy"], "mcc": o["mcc"],
            "top2_accuracy": o["top2_accuracy"], "log_loss": o["log_loss"], "ece": o["ece"],
            "fit_seconds": t.get("fit_seconds"), "predict_ms_per_100": t.get("predict_ms_per_100"),
            "train_accuracy": results[n].get("train", {}).get("accuracy"),
            "train_gap": (results[n]["train"]["accuracy"] - o["accuracy"]) if "train" in results[n] and o["accuracy"] is not None else None,
        })

    correct = {n: np.asarray(predictions[n]).astype(str) == y for n in names}
    pairwise = []
    for a, b in itertools.combinations(names, 2):
        m = mcnemar(correct[a], correct[b])
        # mcnemar's "b"/"c" are counts (A right & B wrong / A wrong & B right); model names go in model_a/model_b.
        pairwise.append({"model_a": a, "model_b": b, **m, "significant": bool(m["p_value"] < alpha)})

    f1_table = {c: {n: results[n]["per_class"][c]["f1"] for n in names} for c in classes}
    best_per_class = {}
    for c, row in f1_table.items():
        vals = {n: v for n, v in row.items() if v is not None}
        top = max(vals.values()) if vals else None
        best_per_class[c] = [n for n, v in vals.items() if top is not None and np.isclose(v, top)]

    vs_baseline = {}
    if baseline in results:
        base = results[baseline]
        for n in names:
            if n == baseline:
                continue
            worse = [
                c for c in classes
                if base["per_class"][c]["f1"] is not None and (results[n]["per_class"][c]["f1"] or 0.0) < base["per_class"][c]["f1"] - 1e-12
            ]
            vs_baseline[n] = {
                "macro_f1_gain": (results[n]["overall"]["macro_f1"] or 0.0) - (base["overall"]["macro_f1"] or 0.0),
                "worse_classes": worse,
                "mcnemar_p": _pair(pairwise, n, baseline)["p_value"],
            }

    tfidf_vs_embed = []
    for kind in ("lr", "linear_svc", "rf"):
        a, b = f"tfidf/{kind}", f"embeddings/{kind}"
        if a in results and b in results:
            m = _pair(pairwise, a, b)
            tfidf_vs_embed.append({
                "model": kind, "tfidf_macro_f1": results[a]["overall"]["macro_f1"], "embeddings_macro_f1": results[b]["overall"]["macro_f1"],
                "tfidf_ece": results[a]["overall"]["ece"], "embeddings_ece": results[b]["overall"]["ece"],
                "p_value": m["p_value"], "significant": m["significant"],
            })

    return {
        "classes": classes,
        "n_rows": int(len(y)),
        "alpha": alpha,
        "leaderboard": leaderboard,
        "mcnemar": pairwise,
        "per_class_f1": f1_table,
        "best_per_class": best_per_class,
        "vs_baseline": vs_baseline,
        "tfidf_vs_embeddings": tfidf_vs_embed,
        "recommendation": recommend(results, pairwise, baseline, alpha),
        "warnings": warnings(results, vs_baseline, pairwise, baseline, alpha),
    }


def _pair(pairwise: list[dict], a: str, b: str) -> dict:
    """The McNemar row for models a and b, in either order."""
    for p in pairwise:
        if {p["model_a"], p["model_b"]} == {a, b}:
            return p
    raise KeyError((a, b))


def _overlap(r1: dict, r2: dict) -> bool:
    """True if the two models' macro-F1 bootstrap intervals overlap."""
    l1, h1 = _ci(r1)
    l2, h2 = _ci(r2)
    if None in (l1, h1, l2, h2):
        return True
    return l1 <= h2 and l2 <= h1


def recommend(results: dict, pairwise: list[dict], baseline: str = BASELINE, alpha: float = ALPHA) -> dict[str, Any]:
    """Best trained model by macro-F1; if statistically tied with others, prefer the simpler one (LR > LinearSVC > RF)."""
    models = sorted([n for n in results if n != baseline], key=lambda n: -(results[n]["overall"]["macro_f1"] or 0.0))
    if not models:
        return {"model": None, "reason": "no trained models to compare"}
    best = models[0]
    tied = [best] + [
        n for n in models[1:]
        if _overlap(results[best], results[n]) and not _pair(pairwise, best, n)["significant"]
    ]
    out: dict[str, Any] = {"best_by_macro_f1": best, "statistically_tied_with_best": tied[1:]}
    if len(tied) == 1:
        out["model"] = best
        out["reason"] = f"{best} has the highest macro-F1 and is significantly better than or clearly separated from every other model"
    else:
        # Simplest model type first; then lower ECE (better calibrated); then the higher macro-F1.
        def key(n: str) -> tuple:
            ece = results[n]["overall"]["ece"]
            return (SIMPLICITY.index(_kind(n)), ece if ece is not None else 1.0, -(results[n]["overall"]["macro_f1"] or 0.0))

        pick = min(tied, key=key)
        out["model"] = pick
        out["reason"] = (
            f"{len(tied)} models are statistically tied with the best ({', '.join(tied)}): their macro-F1 intervals overlap "
            f"and McNemar p >= {alpha}. Picked {pick}: {WHY_SIMPLER[_kind(pick)]}"
            + (f"; among equally simple ones it has the lowest ECE." if sum(_kind(n) == _kind(pick) for n in tied) > 1 else ".")
        )
        eces = {n: results[n]["overall"]["ece"] for n in tied if results[n]["overall"]["ece"] is not None}
        if pick in eces and eces:
            best_cal = min(eces, key=eces.get)
            if eces[pick] - eces[best_cal] > ECE_NOTE_GAP:
                out["calibration_note"] = (
                    f"Its probabilities are less well calibrated (ECE {eces[pick]:.3f} vs {eces[best_cal]:.3f} for {best_cal}): "
                    f"calibrate it on the validation split before showing its confidence to anyone."
                )
                out["reason"] += " " + out["calibration_note"]
    if baseline in results:
        p = _pair(pairwise, out["model"], baseline)
        out["vs_baseline_p"] = p["p_value"]
        out["beats_baseline_significantly"] = bool(
            p["significant"] and (results[out["model"]]["overall"]["macro_f1"] or 0) > (results[baseline]["overall"]["macro_f1"] or 0)
        )
    return out


def warnings(results: dict, vs_baseline: dict, pairwise: list[dict], baseline: str = BASELINE, alpha: float = ALPHA) -> list[str]:
    """Leakage / too-easy data, weak classes, and models that don't beat the baseline."""
    out = []
    for n, r in results.items():
        f1 = r["overall"]["macro_f1"]
        if f1 is not None and f1 > LEAK_F1:
            out.append(f"{n}: test macro-F1 {f1:.3f} > {LEAK_F1}: possible label leakage, or synthetic data that is too easy.")
        for c, m in r["per_class"].items():
            if m["recall"] is not None and m["recall"] < LOW_RECALL:
                out.append(f"{n}: class {c} recall {m['recall']:.2f} < {LOW_RECALL}.")
    for n, d in vs_baseline.items():
        if d["macro_f1_gain"] <= 0:
            out.append(f"{n}: does not beat the {baseline} baseline (macro-F1 gain {d['macro_f1_gain']:+.3f}).")
        elif d["mcnemar_p"] >= alpha:
            out.append(f"{n}: beats the {baseline} baseline by {d['macro_f1_gain']:+.3f} macro-F1, but not significantly (McNemar p = {d['mcnemar_p']:.3f}).")
    return out


def to_markdown(report: dict[str, Any], results: dict[str, dict[str, Any]], extra: dict[str, Any] | None = None) -> str:
    """Render the comparison as a Markdown report."""
    extra = extra or {}
    rec = report["recommendation"]
    lines = ["# UC4 failure-class models: test-set comparison", ""]
    lines += [f"Test split: {report['n_rows']} rows. Classes: {', '.join(report['classes'])}. "
              f"Intervals: 95% bootstrap over {extra.get('bootstrap_note', 'cases')}. Significance: alpha = {report['alpha']}.", ""]
    for note in extra.get("notes", []):
        lines.append(f"- {note}")
    lines += ["", "## Recommendation", "", f"**{rec.get('model')}**. {rec.get('reason', '')}", ""]
    if "vs_baseline_p" in rec:
        verdict = "significantly better than" if rec["beats_baseline_significantly"] else "NOT significantly better than"
        lines += [f"It is {verdict} the rules baseline (McNemar p = {rec['vs_baseline_p']:.3g}).", ""]

    lines += ["## Leaderboard (sorted by macro-F1)", "",
              "| Model | Macro-F1 [95% CI] | Train acc | Test acc | Gap | Balanced acc | MCC | Top-2 acc | Log loss | ECE | Fit s | Predict ms / 100 rows |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["leaderboard"]:
        gap = "N/A" if r.get("train_gap") is None else f"{r['train_gap']:+.3f}"
        lines.append(
            f"| {r['model']} | {_fmt(r['macro_f1'])} [{_fmt(r['macro_f1_low'])}, {_fmt(r['macro_f1_high'])}] | "
            f"{_fmt(r.get('train_accuracy'))} | {_fmt(r['accuracy'])} | {gap} | "
            f"{_fmt(r['balanced_accuracy'])} | {_fmt(r['mcc'])} | {_fmt(r['top2_accuracy'])} | {_fmt(r['log_loss'])} | {_fmt(r['ece'])} | "
            f"{_fmt(r['fit_seconds'], 1)} | {_fmt(r['predict_ms_per_100'], 1)} |"
        )
    if extra.get("without_insufficient"):
        lines += ["", f"Macro-F1 without the insufficient-evidence test cases ({extra['without_insufficient']['n_rows']} rows): "
                  + ", ".join(f"{n} {_fmt(v)}" for n, v in extra["without_insufficient"]["macro_f1"].items())]

    names = [r["model"] for r in report["leaderboard"]]
    lines += ["", "## Per-class F1 (best per row in bold)", "", "| Class | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for c, row in report["per_class_f1"].items():
        cells = [f"**{_fmt(row[n])}**" if n in report["best_per_class"][c] else _fmt(row[n]) for n in names]
        lines.append(f"| {c} | " + " | ".join(cells) + " |")

    winner = rec.get("model")
    if winner:
        pc = results[winner]["per_class"]
        lines += ["", f"## One-vs-rest counts for {winner}", "",
                  "| Class | Support | TP | FP | FN | TN | Precision | Recall | Specificity | F1 | FPR | FNR | ROC-AUC | PR-AUC |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c, m in pc.items():
            lines.append(f"| {c} | {m['support']} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {_fmt(m['precision'])} | {_fmt(m['recall'])} | "
                         f"{_fmt(m['specificity'])} | {_fmt(m['f1'])} | {_fmt(m['fpr'])} | {_fmt(m['fnr'])} | {_fmt(m['roc_auc'])} | {_fmt(m['pr_auc'])} |")
        lines += ["", f"Most-confused pairs for {winner}:", ""]
        mc = results[winner]["most_confused"]
        lines += [f"- {p['true']} -> {p['predicted']}: {p['count']} rows ({_fmt(p['share_of_true_class'], 2)} of {p['true']})" for p in mc] or ["- none"]

    lines += ["", "## Gain over the rules baseline", "", "| Model | Macro-F1 gain | McNemar p | Classes worse than baseline |", "|---|---|---|---|"]
    for n, d in report["vs_baseline"].items():
        lines.append(f"| {n} | {d['macro_f1_gain']:+.3f} | {d['mcnemar_p']:.3g} | {', '.join(d['worse_classes']) or 'none'} |")

    if report["tfidf_vs_embeddings"]:
        lines += ["", "## TF-IDF vs embeddings (same model type)", "", "| Model | TF-IDF macro-F1 | Embeddings macro-F1 | TF-IDF ECE | Embeddings ECE | McNemar p | Significant |", "|---|---|---|---|---|---|---|"]
        for r in report["tfidf_vs_embeddings"]:
            lines.append(f"| {r['model']} | {_fmt(r['tfidf_macro_f1'])} | {_fmt(r['embeddings_macro_f1'])} | {_fmt(r['tfidf_ece'])} | "
                         f"{_fmt(r['embeddings_ece'])} | {r['p_value']:.3g} | {'yes' if r['significant'] else 'no'} |")

    lines += ["", "## McNemar tests (every pair)", "", "| A | B | A right, B wrong | A wrong, B right | Statistic | p-value | Method | Significant |", "|---|---|---|---|---|---|---|---|"]
    for p in report["mcnemar"]:
        lines.append(f"| {p['model_a']} | {p['model_b']} | {p['b']} | {p['c']} | {p['statistic']:.3g} | {p['p_value']:.3g} | "
                     f"{p['method']} | {'yes' if p['significant'] else 'no'} |")
    lines += ["", "Rows inside one case are near-copies, so McNemar (which assumes independent rows) overstates significance; "
              "treat p-values near alpha with care and prefer the case-level intervals."]

    lines += ["", "## Warnings", ""]
    lines += [f"- {w}" for w in report["warnings"]] or ["- none"]
    return "\n".join(lines) + "\n"

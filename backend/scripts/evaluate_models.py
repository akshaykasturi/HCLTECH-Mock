"""Evaluate the saved UC4 failure-class models on the shared test split and compare them. No refitting.

Run from backend:  .\\.venv\\Scripts\\python.exe scripts\\evaluate_models.py --features all --split random|grouped
random writes backend/data/eval/metrics.json, model_comparison.md and plots/; grouped writes the same names with a
_grouped suffix, so a grouped run never overwrites the random-split outputs.
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable

from app.uc4.ml.compare_models import compare, to_markdown  # noqa: E402
from app.uc4.ml.eval_metrics import evaluate  # noqa: E402
from app.uc4.ml.features import EVAL_DIR, get_group_cases, get_group_split, get_groups, get_split  # noqa: E402
from app.uc4.ml.train_models import FEATURE_SETS, MODEL_DIR, load_models  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND / "data" / "eval"


def _proba(bundle: dict, X, classes: list[str]) -> np.ndarray | None:
    """Probabilities in `classes` column order: the calibrated model if there is one, else the model's own, else None."""
    source = bundle["calibrated"] or bundle["model"]
    if not hasattr(source, "predict_proba"):
        return None
    p = source.predict_proba(X)
    order = [list(source.classes_).index(c) for c in classes]
    return p[:, order]


def insufficient_case_ids() -> set[str]:
    """Test cases with no labelled cause (expected outcome CLARIFY)."""
    with open(EVAL_DIR / "cases.jsonl", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]
    return {c["case_id"] for c in cases if c["expected_cause"] is None}


def plots(results: dict, report: dict, out: Path) -> list[str]:
    """Confusion heatmaps per model, one reliability diagram, one per-class F1 bar chart. Returns file names."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logging.warning("matplotlib not installed: skipping plots")
        return []
    out.mkdir(parents=True, exist_ok=True)
    written = []
    classes = report["classes"]
    for name, r in results.items():
        counts = np.array(r["confusion"]["counts"])
        norm = np.array([[np.nan if v is None else v for v in row] for row in r["confusion"]["row_normalised"]])
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
        for ax, data, title, fmt in ((axes[0], counts, "counts", "d"), (axes[1], norm, "row-normalised", ".2f")):
            im = ax.imshow(data, cmap="Blues", vmin=0)
            ax.set_xticks(range(len(classes)), classes, rotation=45, ha="right")
            ax.set_yticks(range(len(classes)), classes)
            ax.set_xlabel("predicted")
            ax.set_ylabel("true")
            ax.set_title(f"{name}: {title}")
            top = np.nanmax(data) if np.isfinite(data).any() else 1
            for i in range(len(classes)):
                for j in range(len(classes)):
                    v = data[i, j]
                    if np.isfinite(v):
                        ax.text(j, i, format(int(v) if fmt == "d" else v, fmt), ha="center", va="center",
                                color="white" if v > top / 2 else "black", fontsize=8)
            fig.colorbar(im, ax=ax, fraction=0.046)
        fig.tight_layout()
        fname = f"confusion_{name.replace('/', '__')}.png"
        fig.savefig(out / fname, dpi=120)
        plt.close(fig)
        written.append(fname)

    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.plot([0, 1], [0, 1], "--", color="grey", label="perfect calibration")
    for name, r in results.items():
        if r["reliability"]:
            pts = [(b["confidence"], b["accuracy"]) for b in r["reliability"] if b["count"]]
            ax.plot(*zip(*pts), marker="o", label=f"{name} (ECE {r['overall']['ece']:.3f})")
    ax.set_xlabel("mean confidence (top label)")
    ax.set_ylabel("accuracy")
    ax.set_title("Reliability diagram (test split, 10 bins)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "reliability.png", dpi=120)
    plt.close(fig)
    written.append("reliability.png")

    names = [r["model"] for r in report["leaderboard"]]
    width = 0.8 / len(names)
    fig, ax = plt.subplots(figsize=(12, 5))
    for k, n in enumerate(names):
        vals = [report["per_class_f1"][c][n] or 0.0 for c in classes]
        ax.bar(np.arange(len(classes)) + k * width, vals, width, label=n)
    ax.set_xticks(np.arange(len(classes)) + 0.4 - width / 2, classes, rotation=30, ha="right")
    ax.set_ylabel("F1")
    ax.set_ylim(0, 1.05)
    ax.set_title("Per-class F1 on the test split")
    ax.legend(fontsize=8, ncol=4)
    fig.tight_layout()
    fig.savefig(out / "per_class_f1.png", dpi=120)
    plt.close(fig)
    written.append("per_class_f1.png")
    return written


def main() -> None:
    """Load models, evaluate on the test split, compare, write JSON/Markdown/plots, print the leaderboard."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", choices=["embeddings", "tfidf", "all"], default="all")
    parser.add_argument("--split", choices=["random", "grouped"], default="random")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    sets = list(FEATURE_SETS) if args.features == "all" else [args.features]
    bundles = load_models(sets, args.split)
    if not bundles:
        sys.exit(f"No models in {MODEL_DIR}. Train them first: .\\.venv\\Scripts\\python.exe scripts\\train_models.py")
    summary_path = MODEL_DIR / args.split / "training_summary.json"
    training = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    if args.split == "grouped":
        X_train, X_test, y_train, y_test = get_group_split()
        groups = get_group_cases(X_test.index).to_numpy()
    else:
        X_train, X_test, y_train, y_test = get_split()
        groups = get_groups("test").to_numpy()
    suffix = "" if args.split == "random" else "_grouped"
    classes = sorted(y_train.unique())
    y = y_test.to_numpy()
    insufficient = np.isin(groups, list(insufficient_case_ids()))

    results: dict[str, Any] = {}
    predictions: dict[str, np.ndarray] = {}
    timings: dict[str, dict[str, float]] = {}
    without_insufficient: dict[str, float | None] = {}
    for name, bundle in bundles.items():
        if list(bundle["classes"]) != classes:
            sys.exit(f"{name}: class order {bundle['classes']} != {classes}")
        start = time.perf_counter()
        pred = np.asarray(bundle["model"].predict(X_test))
        proba = _proba(bundle, X_test, classes)
        elapsed = time.perf_counter() - start
        timings[name] = {"fit_seconds": training.get(name, {}).get("fit_seconds"), "predict_ms_per_100": elapsed / len(X_test) * 100 * 1000}
        predictions[name] = pred
        results[name] = evaluate(y, pred, proba, classes, groups=groups)
        results[name]["training"] = training.get(name, {})
        # Score on the rows the model was trained on (prediction only, no refit): a large gap = overfitting.
        train_pred = np.asarray(bundle["model"].predict(X_train))
        results[name]["train"] = {
            "rows": int(len(X_train)),
            "accuracy": float(accuracy_score(y_train, train_pred)),
            "macro_f1": float(f1_score(y_train, train_pred, average="macro", zero_division=0)),
        }
        sub = evaluate(y[~insufficient], pred[~insufficient], None if proba is None else proba[~insufficient], classes, n_boot=1)
        without_insufficient[name] = sub["overall"]["macro_f1"]

    report = compare(results, predictions, y, timings)
    extra = {
        "bootstrap_note": f"{len(np.unique(groups))} test cases (1000 resamples, seed 42)",
        "notes": [
            ("Same rows for every model: the fixed case-grouped test split (classifier_test.csv)" if args.split == "random" else
             "Same rows for every model: the template-grouped test split (test_idx_grouped.json): one message template per class "
             "never seen in training") + "; identical class order checked.",
            "LinearSVC: predictions from the model itself, probabilities from its sigmoid calibration "
            + ("on the validation split." if args.split == "random" else "by grouped cross-validation on train."),
            "rules = most common class per HTTP status in train; it has no probabilities (probability metrics N/A).",
            "Embedding prediction times use the on-disk vector cache; a cold first call is slower.",
        ],
        "without_insufficient": {"n_rows": int((~insufficient).sum()), "macro_f1": without_insufficient},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"split": args.split, "classes": classes, "n_test_rows": len(y), "models": results, "comparison": report, "timings": timings, "extra": extra}
    (OUT_DIR / f"metrics{suffix}.json").write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    (OUT_DIR / f"model_comparison{suffix}.md").write_text(to_markdown(report, results, extra), encoding="utf-8")
    written = plots(results, report, OUT_DIR / f"plots{suffix}")

    print(f"{'model':<24} {'macro-F1 [95% CI]':<24} {'acc':>6} {'bal acc':>8} {'MCC':>6} {'ECE':>6}")
    for r in report["leaderboard"]:
        ci = f"{r['macro_f1']:.3f} [{r['macro_f1_low']:.3f}, {r['macro_f1_high']:.3f}]"
        ece = "N/A" if r["ece"] is None else f"{r['ece']:.3f}"
        print(f"{r['model']:<24} {ci:<24} {r['accuracy']:>6.3f} {r['balanced_accuracy']:>8.3f} {r['mcc']:>6.3f} {ece:>6}")
    rec = report["recommendation"]
    print(f"\nRecommendation: {rec['model']}. {rec['reason']}")
    for w in report["warnings"]:
        print(f"WARNING: {w}")
    print(f"\nWrote {OUT_DIR / f'metrics{suffix}.json'}, {OUT_DIR / f'model_comparison{suffix}.md'} "
          f"and {len(written)} plots in {OUT_DIR / f'plots{suffix}'}")


def _json_default(o: Any) -> Any:
    """Make numpy scalars and arrays JSON-serialisable."""
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


if __name__ == "__main__":
    main()

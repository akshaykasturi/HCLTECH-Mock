"""Random vs template-grouped split: how much of the 0.98 survives on message wordings never seen in training?

Run from backend (after train_models.py and evaluate_models.py for both splits, and robustness_checks.py):
    .\\.venv\\Scripts\\python.exe scripts\\split_comparison.py
It also runs the 3-round template rotation: each round holds out one template per class, trains every model on
the rest (tuning on train only, template-grouped folds) and scores the held-out rows. Rotation models are not saved.
Writes backend/data/eval/split_comparison.md and split_comparison.json.
"""
import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable

from app.uc4.ml.features import N_ROTATIONS, _split_by_templates, _template_owner, load_pool, template_rotations  # noqa: E402
from app.uc4.ml.train_models import fit_all  # noqa: E402

EVAL = Path(__file__).resolve().parents[1] / "data" / "eval"
FEATURE_SETS = ["tfidf", "embeddings"]


def rotation() -> dict:
    """Train and score every model on each rotation round; returns per-round scores and held-out templates."""
    X, y, meta = load_pool()
    owner = _template_owner(meta, y)
    rounds = []
    for r, held in enumerate(template_rotations(meta, y, N_ROTATIONS)):
        X_tr, X_te, y_tr, y_te = _split_by_templates(X, y, meta, held)
        data = {"X": X_tr, "y": y_tr, "groups": meta.loc[X_tr.index, "template_id"], "X_val": None, "y_val": None}
        bundles, _ = fit_all(data, FEATURE_SETS, "grouped")
        scores = {}
        for name, b in bundles.items():
            pred = b["model"].predict(X_te)
            scores[name] = {"macro_f1": float(f1_score(y_te, pred, average="macro", zero_division=0)),
                            "accuracy": float(accuracy_score(y_te, pred))}
        rounds.append({"round": r, "test_rows": int(len(X_te)), "held_out": {owner[t]: t for t in held}, "scores": scores})
        print(f"round {r}: {len(X_te)} test rows; " + ", ".join(f"{n} {s['macro_f1']:.3f}" for n, s in scores.items()))
    return {"rounds": rounds}


def _load(name: str) -> dict | None:
    """Read a JSON output of the other scripts, or None if it hasn't been produced."""
    path = EVAL / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    """Build the comparison report."""
    logging.basicConfig(level=logging.WARNING)
    warnings.filterwarnings("ignore")
    random_m, grouped_m = _load("metrics.json"), _load("metrics_grouped.json")
    if random_m is None or grouped_m is None:
        sys.exit("Run evaluate_models.py --split random and --split grouped first.")
    rot = rotation()
    names = [r["model"] for r in random_m["comparison"]["leaderboard"]]

    def ci(m: dict, n: str) -> str:
        b = m["models"][n]["bootstrap_95ci"]["macro_f1"]
        return f"{b['point']:.3f} [{b['low']:.3f}, {b['high']:.3f}]"

    def acc(m: dict, n: str) -> str:
        train = m["models"][n].get("train", {}).get("accuracy")
        test = m["models"][n]["overall"]["accuracy"]
        return f"{'N/A' if train is None else f'{train:.3f}'} / {test:.3f}"

    md = ["# Random vs template-grouped split", "",
          "**random**: the fixed case-grouped split. All 303 test rows use a message template that also appears in train.",
          f"**grouped**: one message template per class held out (`backend/data/splits/test_idx_grouped.json`, "
          f"{grouped_m['n_test_rows']} test rows); every test row uses wording never seen in training.",
          f"**rotation**: {N_ROTATIONS} rounds, a different template per class held out each round; mean and range of macro-F1.",
          "Intervals: 95% bootstrap over test cases. Status code and error code stay visible in every mode.", "",
          "## Macro-F1 by split", "",
          "| Model | Random macro-F1 [95% CI] | Random train / test acc | Grouped macro-F1 [95% CI] | Grouped train / test acc "
          "| Macro-F1 drop | Rotation macro-F1 mean (min to max) |", "|---|---|---|---|---|---|---|"]
    rows = {}
    for n in names:
        rf = random_m["models"][n]["overall"]["macro_f1"]
        gf = grouped_m["models"][n]["overall"]["macro_f1"]
        rot_f1 = [r["scores"][n]["macro_f1"] for r in rot["rounds"]]
        rows[n] = {"random": rf, "grouped": gf, "rotation": rot_f1}
        md.append(f"| {n} | {ci(random_m, n)} | {acc(random_m, n)} | {ci(grouped_m, n)} | {acc(grouped_m, n)} | {gf - rf:+.3f} | "
                  f"{np.mean(rot_f1):.3f} ({min(rot_f1):.3f} to {max(rot_f1):.3f}) |")

    md += ["", "Held-out templates per rotation round:", ""]
    for r in rot["rounds"]:
        md.append(f"- round {r['round']} ({r['test_rows']} rows): " + "; ".join(f"{c}: `{t}`" for c, t in sorted(r["held_out"].items())))

    grouped_cmp = grouped_m["comparison"]
    md += ["", "## Grouped split: recommendation and warnings", "",
           f"**{grouped_cmp['recommendation'].get('model')}**. {grouped_cmp['recommendation'].get('reason', '')}", ""]
    md += [f"- {w}" for w in grouped_cmp["warnings"]] or ["- none"]

    for split, fname in (("random", "robustness.json"), ("grouped", "robustness_grouped.json")):
        rob = _load(fname)
        if rob is None:
            md += ["", f"## Robustness ({split} split): not run yet (scripts/robustness_checks.py --split {split})"]
            continue
        kinds = [k for k in next(iter(rob["perturbation"].values())) if k != "original"]
        md += ["", f"## Robustness ({split} split)", "", "Perturbed test lines, trained models unchanged. Cells: accuracy (share of predictions that flipped).", "",
               "| Model | original | " + " | ".join(kinds) + " |", "|---" * (len(kinds) + 2) + "|"]
        for n, cells in rob["perturbation"].items():
            md.append(f"| {n} | " + " | ".join(f"{a:.3f} ({f:.0%})" for a, f in cells.values()) + " |")
        md += ["", "Retrained without columns (test accuracy):", "", "| Model | full | no status+code | text only |", "|---|---|---|---|"]
        for n, row in rob["ablation"].items():
            md.append(f"| {n} | {row['full'][1]:.3f} | {row['no_status_code'][1]:.3f} | {row['text_only'][1]:.3f} |")

    (EVAL / "split_comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (EVAL / "split_comparison.json").write_text(json.dumps({"macro_f1": rows, "rotation": rot}, indent=2), encoding="utf-8")
    print(f"\nWrote {EVAL / 'split_comparison.md'} and {EVAL / 'split_comparison.json'}")


if __name__ == "__main__":
    main()

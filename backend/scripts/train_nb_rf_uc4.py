"""Tune and train the UC4 ComplementNB and RandomForest cause classifiers; report on validation.

Run from backend:  .venv/bin/python -m scripts.train_nb_rf_uc4
Fits on train only, tunes on validation only, never loads test.
Saves the chosen models to backend/models/uc4/ (git-ignored).
"""
from pathlib import Path

import joblib
import numpy as np

from app.uc4.evaluate_classifier import confused_pairs, score_cases
from app.uc4.ml.cause_data import load_cause_split
from app.uc4.nb_rf import MODELS, tune

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "uc4"


def fmt(ci: tuple[float, float, float]) -> str:
    """0.929 [0.786, 1.000]"""
    return f"{ci[0]:.3f} [{ci[1]:.3f}, {ci[2]:.3f}]"


def main() -> None:
    train, validation = load_cause_split("train"), load_cause_split("validation")
    focal = validation.focal()
    labelled, unsure = focal.labelled(), focal.take(focal.insufficient)
    print(f"train: {len(train)} rows, {len(set(train.case_id))} cases | validation: "
          f"{len(labelled)} cases with a cause + {len(unsure)} insufficient (scored separately)\n")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, (build, grid) in MODELS.items():
        model, rows = tune(build, grid, train, validation)
        print(f"{name} grid (validation, {len(labelled)} cases):")
        for r in rows:
            print(f"  {r['params']}  macro-F1 {r['macro_f1']:.3f}  brier {r['brier']:.3f}")
        print(f"  chosen: {model.describe()}\n")
        path = MODEL_DIR / f"{model.model_name}_{model.feature_set}.joblib"
        joblib.dump(model, path)
        labels, top, _ = model.predict(labelled.X)
        results[name] = (model, path, score_cases(labelled.y.astype(str), labels, top), labels, top)

    print(f"Validation, per case (focal row), n = {len(labelled)}, 95% bootstrap intervals")
    print(f"{'model':<54}{'accuracy':<24}{'macro-F1':<24}{'ECE':<24}{'Brier':<24}")
    for model, _, s, _, _ in results.values():
        print(f"{model.describe():<54}" + "".join(f"{fmt(s[m]):<24}" for m in ("accuracy", "macro_f1", "ece", "brier")))

    rows_lab = validation.labelled()
    for name, (model, path, _, labels, top) in results.items():
        print(f"\n{name}: saved to {path.relative_to(MODEL_DIR.parents[1])}")
        pairs = confused_pairs(labelled.y, labels)
        print(f"  most confused, per case ({len(pairs)} distinct mistakes):")
        for t, p, n in pairs:
            print(f"    {t} -> {p}: {n}")
        row_labels, _, _ = model.predict(rows_lab.X)
        print(f"  most confused, all {len(rows_lab)} validation lines (context; lines of a case are near-copies):")
        for t, p, n in confused_pairs(rows_lab.y, row_labels):
            print(f"    {t} -> {p}: {n}")
        u_labels, u_top, _ = model.predict(unsure.X)
        for c, l, p in zip(unsure.case_id, u_labels, u_top):
            print(f"  insufficient case {c}: top guess {l} at {p:.2f} (should be CLARIFY)")
        print(f"  mean top probability, right answers {np.mean(top[labels == labelled.y]):.2f}, "
              f"wrong answers {np.mean(top[labels != labelled.y]) if (labels != labelled.y).any() else float('nan'):.2f}")


if __name__ == "__main__":
    main()

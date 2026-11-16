"""Publish one trained UC4 model: copy it to backend/models_release/uc4/ with a model card and README.

Run from backend (after train_models.py and evaluate_models.py for both splits):
    .\\.venv\\Scripts\\python.exe scripts\\release_model.py --model tfidf/linear_svc --split random
Every number in the README and model_card.json is read from the generated metrics files, never typed by hand.
"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import sklearn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable

from app.uc4.ml.train_models import MODEL_DIR  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
EVAL = BACKEND / "data" / "eval"
RELEASE = BACKEND / "models_release" / "uc4"


def _metrics(split: str) -> dict:
    """The evaluate_models.py output for a split."""
    return json.loads((EVAL / f"metrics{'' if split == 'random' else '_grouped'}.json").read_text(encoding="utf-8"))


def main() -> None:
    """Copy the model, write model_card.json and README.md."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="tfidf/linear_svc")
    parser.add_argument("--split", choices=["random", "grouped"], default="random")
    args = parser.parse_args()

    source = MODEL_DIR / args.split / f"{args.model.replace('/', '__')}.joblib"
    if not source.exists():
        sys.exit(f"{source} not found: run scripts/train_models.py --split {args.split}")
    RELEASE.mkdir(parents=True, exist_ok=True)
    target = RELEASE / f"failure_class_{args.model.replace('/', '__')}.joblib"
    shutil.copyfile(source, target)
    sha = hashlib.sha256(target.read_bytes()).hexdigest()

    m = _metrics(args.split)[ "models"][args.model]
    other_split = "grouped" if args.split == "random" else "random"
    other = _metrics(other_split)["models"].get(args.model)
    o, b, t = m["overall"], m["bootstrap_95ci"]["macro_f1"], m.get("train", {})
    card = {
        "name": f"uc4-failure-class-{args.model.replace('/', '-')}",
        "task": "classify one failing API log line into 7 failure classes",
        "classes": m["classes"],
        "model": args.model,
        "trained_on_split": args.split,
        "training": m.get("training", {}),
        "train": t,
        "test": {k: o[k] for k in ("n", "accuracy", "macro_f1", "balanced_accuracy", "weighted_f1", "mcc", "cohen_kappa",
                                   "top2_accuracy", "log_loss", "brier", "ece")},
        "test_macro_f1_95ci": [b["low"], b["high"]],
        "test_on_unseen_wording": None if other is None else {"split": other_split, "accuracy": other["overall"]["accuracy"],
                                                              "macro_f1": other["overall"]["macro_f1"]},
        "per_class_f1": {c: v["f1"] for c, v in m["per_class"].items()},
        "file": target.name,
        "sha256": sha,
        "scikit_learn_version": sklearn.__version__,
        "released": date.today().isoformat(),
    }
    (RELEASE / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")

    f = lambda v: "N/A" if v is None else f"{v:.3f}"  # noqa: E731
    # Why this model: among the models tied with the best, compare probability quality (log loss, Brier, ECE).
    split_m = _metrics(args.split)
    rec = split_m["comparison"]["recommendation"]
    tied = [rec["best_by_macro_f1"], *rec.get("statistically_tied_with_best", [])]
    why_rows = "\n".join(
        f"| {n} | {f(split_m['models'][n]['overall']['macro_f1'])} | {f(split_m['models'][n]['overall']['log_loss'])} | "
        f"{f(split_m['models'][n]['overall']['brier'])} | {f(split_m['models'][n]['overall']['ece'])} |"
        for n in sorted(tied, key=lambda n: split_m["models"][n]["overall"]["log_loss"] or 9)
    )
    why = (
        f"`model_comparison.md` finds {len(tied)} models statistically tied on macro-F1 and its tie rule picks the simplest "
        f"type ({rec['model']}). This release instead picks the tied model with the best probabilities (lowest log loss and Brier), "
        f"because the pipeline shows and acts on the model's confidence.\n\n"
        f"| Tied model | Test macro-F1 | Log loss | Brier | ECE |\n|---|---|---|---|---|\n{why_rows}\n"
    )
    per_class = "\n".join(f"| {c} | {f(v)} |" for c, v in card["per_class_f1"].items())
    unseen = card["test_on_unseen_wording"]
    readme = f"""# UC4 failure-class model: `{args.model}`

Released by `scripts/release_model.py`; every number below comes from `backend/data/eval/metrics*.json`.
Full reports: `backend/data/eval/model_comparison.md`, `split_comparison.md`, `robustness.md`; plots in `backend/data/eval/plots/`.

## What it is
LinearSVC on the shared TF-IDF features (`app/uc4/ml/features.py`: cleaned message word + char TF-IDF, one-hot status /
route / error code / upstream error, scaled numbers, 0/1 flags), tuned on the train split with case-grouped folds
(best params `{card['training'].get('best_params')}`). Predicts one of: {', '.join(card['classes'])}.

## Why this model
{why}
## Scores ({args.split} split)

| | Train | Test |
|---|---|---|
| Rows | {t.get('rows', 'N/A')} | {o['n']} |
| Accuracy | {f(t.get('accuracy'))} | {f(o['accuracy'])} |
| Macro-F1 | {f(t.get('macro_f1'))} | {f(o['macro_f1'])} [95% CI {f(b['low'])} to {f(b['high'])}] |

Test: balanced accuracy {f(o['balanced_accuracy'])}, MCC {f(o['mcc'])}, top-2 accuracy {f(o['top2_accuracy'])},
log loss {f(o['log_loss'])}, Brier {f(o['brier'])}, ECE {f(o['ece'])}.

| Class | Test F1 |
|---|---|
{per_class}

## Limits (read before using it)
- On message wording never seen in training ({unseen['split'] if unseen else 'grouped'} split) the same model type scores
  accuracy {f(unseen['accuracy']) if unseen else 'N/A'}, macro-F1 {f(unseen['macro_f1']) if unseen else 'N/A'}: no better than predicting
  from the HTTP status code alone. See `split_comparison.md`.
- Synthetic data: the status code nearly decides the class, so high scores here say little about real logs.
- Probabilities: use the calibrated model stored next to it (`bundle["calibrated"]`); the raw LinearSVC has none.

## How to load
```python
import joblib
from app.uc4.ml.features import parse_lines

bundle = joblib.load("models_release/uc4/{target.name}")   # from backend; trusted file only (pickle)
X = parse_lines(["status=429 route=POST /v1/payments code=ERR_RATE_LIMITED message=Too many requests"])
label = bundle["model"].predict(X)[0]
probs = dict(zip(bundle["calibrated"].classes_, bundle["calibrated"].predict_proba(X)[0]))
```
Needs scikit-learn {card['scikit_learn_version']} (pinned in `requirements.txt`). File sha256: `{sha}`.
Rebuild instead of trusting the file: `scripts/train_models.py --split {args.split}` (seed 42, deterministic).
"""
    (RELEASE / "README.md").write_text(readme, encoding="utf-8")
    print(f"Released {target} ({target.stat().st_size // 1024} KB), model_card.json and README.md")


if __name__ == "__main__":
    main()

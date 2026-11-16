"""Train the UC4 failure-class models (rules baseline, LR, LinearSVC, RF) and save them to backend/models/uc4/<split>/.

Run from backend:  .\\.venv\\Scripts\\python.exe scripts\\train_models.py --features all --split random|grouped
random:  the case-grouped split; tuning with case-grouped folds; LinearSVC calibrated on the validation split.
grouped: one message template per class held out; GroupKFold by template; LinearSVC calibrated by grouped CV on train.
The test rows are never used here.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable

from app.uc4.ml.train_models import FEATURE_SETS, MODEL_DIR, train_all  # noqa: E402


def main() -> None:
    """Parse --features and train."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", choices=[*FEATURE_SETS, "all"], default="all")
    parser.add_argument("--split", choices=["random", "grouped"], default="random")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("httpx", "huggingface_hub", "fastembed", "app.uc4.ml.embed_features"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    sets = list(FEATURE_SETS) if args.features == "all" else [args.features]
    summary = train_all(sets, args.split)
    print(f"\nSaved to {MODEL_DIR / args.split}")
    print(f"{'model':<24} {'cv f1_macro':>11} {'fit s':>7}  best params")
    for name, info in summary.items():
        cv = f"{info['cv_f1_macro']:.3f}" if "cv_f1_macro" in info else "-"
        print(f"{name:<24} {cv:>11} {info['fit_seconds']:>7.1f}  {info.get('best_params', '')}")


if __name__ == "__main__":
    main()

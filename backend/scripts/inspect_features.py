"""Inspect the shared UC4 features: fit on the train split only and print what the models will see.

Run from backend:  .\\.venv\\Scripts\\python.exe scripts\\inspect_features.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable

from app.uc4.ml.features import CONFIG, build_features, get_split  # noqa: E402

TOP_N = 15


def top_terms_per_class(features, X_train, y_train) -> None:
    """Print the TOP_N word TF-IDF terms with the highest mean weight in each class."""
    vec = features.named_transformers_["text_word"]
    tfidf = vec.transform(X_train[CONFIG["text"]])
    terms = vec.get_feature_names_out()
    for label in sorted(y_train.unique()):
        rows = (y_train == label).to_numpy()
        mean = np.asarray(tfidf[rows].mean(axis=0)).ravel()
        best = np.argsort(mean)[::-1][:TOP_N]
        shown = ", ".join(f"{terms[i]} ({mean[i]:.2f})" for i in best if mean[i] > 0)
        print(f"  {label:<15} n={rows.sum():<4} {shown}")


def main() -> None:
    """Fit both modes on train, print shapes, vocabulary sizes, top terms and the nb non-negative check."""
    X_train, X_test, y_train, y_test = get_split()
    print(f"train rows: {len(X_train)}   test rows: {len(X_test)}")
    print(f"input columns: {list(X_train.columns)}")

    features = build_features("default").fit(X_train)
    Xt_train, Xt_test = features.transform(X_train), features.transform(X_test)
    print(f"\n[default] matrix shape: train {Xt_train.shape}, test {Xt_test.shape}")
    for name in ("text_word", "text_char"):
        print(f"  vocabulary {name}: {len(features.named_transformers_[name].vocabulary_)}")
    sizes = dict(zip(*_names_and_widths(features)))
    print(f"  output width per block: {sizes}")

    print(f"\nTop {TOP_N} word TF-IDF terms per class (mean weight, train split):")
    top_terms_per_class(features, X_train, y_train)

    nb = build_features("nb").fit(X_train)
    mins = [float(m.min()) for m in (nb.transform(X_train), nb.transform(X_test))]
    status = "OK, no negative values" if min(mins) >= 0 else "FAIL, negative values found"
    print(f"\n[nb] min value train={mins[0]:.4f} test={mins[1]:.4f} -> {status}")
    if min(mins) < 0:
        sys.exit(1)


def _names_and_widths(features) -> tuple[list[str], list[int]]:
    """Name and output width of each fitted transformer block."""
    names, widths = [], []
    for name, sl in features.output_indices_.items():
        if name != "remainder":
            names.append(name)
            widths.append(sl.stop - sl.start)
    return names, widths


if __name__ == "__main__":
    main()

"""Score a UC4 cause classifier per case (focal row): accuracy, macro-F1, ECE, Brier, each with a 95% interval."""
from collections import Counter

import numpy as np
from sklearn.metrics import f1_score

from app.analysis.stats import bootstrap_ci, bootstrap_stat, brier, ece


def macro_f1(y_true, y_pred) -> float:
    """Mean F1 over the causes present in y_true or y_pred; every cause counts the same."""
    return float(f1_score(y_true, y_pred, average="macro", zero_division=0))


def score_cases(y_true, labels, top_prob) -> dict:
    """{metric: (point, low, high)} plus n. One item per case; insufficient cases must be left out first."""
    y_true, labels, top_prob = np.asarray(y_true), np.asarray(labels), np.asarray(top_prob, dtype=float)
    correct = (y_true == labels).astype(float)
    return {
        "n": len(y_true),
        "accuracy": bootstrap_ci(correct),
        "macro_f1": bootstrap_stat(macro_f1, y_true, labels),
        "ece": bootstrap_stat(ece, top_prob, correct),
        "brier": bootstrap_stat(brier, top_prob, correct),
    }


def confused_pairs(y_true, labels, k: int = 3) -> list[tuple[str, str, int]]:
    """The k most frequent (true cause, predicted cause, count) mistakes; ties in alphabetical order."""
    wrong = Counter((t, p) for t, p in zip(y_true, labels) if t != p)
    return [(t, p, n) for (t, p), n in sorted(wrong.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

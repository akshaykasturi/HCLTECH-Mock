"""Evaluation metrics for one classifier on the UC4 test split.

evaluate() returns a JSON-ready dict. Anything undefined (no support, no predictions, no probabilities)
is None, shown as "N/A" in reports, never NaN. Bootstrap intervals resample whole cases when case IDs
are given, because rows of one case are near-copies and row resampling would give falsely narrow CIs.
"""
import logging
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    cohen_kappa_score,
    log_loss,
    matthews_corrcoef,
    precision_recall_fscore_support,
    roc_auc_score,
)

logger = logging.getLogger(__name__)

SEED = 42
N_BOOT = 1000
ECE_BINS = 10
TOP_CONFUSED = 5


def _div(num: float, den: float) -> float | None:
    """num / den, or None when den is 0 (undefined, reported as N/A)."""
    return float(num) / float(den) if den else None


def confusion(y_true: np.ndarray, y_pred: np.ndarray, classes: list[str]) -> np.ndarray:
    """Counts matrix: rows = true class, columns = predicted class, in `classes` order."""
    index = {c: i for i, c in enumerate(classes)}
    cm = np.zeros((len(classes), len(classes)), dtype=int)
    for t, p in zip(y_true, y_pred):
        if t in index and p in index:
            cm[index[t], index[p]] += 1
    return cm


def _f1(p: float | None, r: float | None) -> float | None:
    """Harmonic mean of precision and recall; None if either is undefined, 0 if both are 0."""
    if p is None or r is None:
        return None
    return 2 * p * r / (p + r) if (p + r) else 0.0


def _mean(values: list[float | None]) -> float | None:
    """Mean of the defined values, or None if none are defined."""
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else None


def _cm_scores(cm: np.ndarray) -> tuple[float, float | None, float | None]:
    """(accuracy, balanced accuracy, macro-F1) straight from a confusion matrix (fast, for the bootstrap).

    Macro averages use classes with support > 0; a class never predicted counts as F1 = 0.
    """
    tp = np.diag(cm).astype(float)
    support = cm.sum(axis=1).astype(float)
    predicted = cm.sum(axis=0).astype(float)
    present = support > 0
    if not present.any():
        return 0.0, None, None
    recall = tp[present] / support[present]
    precision = np.divide(tp[present], predicted[present], out=np.zeros(present.sum()), where=predicted[present] > 0)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros_like(denom), where=denom > 0)
    return float(tp.sum() / cm.sum()), float(recall.mean()), float(f1.mean())


def per_class(cm: np.ndarray, classes: list[str], y_true: np.ndarray, proba: np.ndarray | None) -> dict[str, dict]:
    """One-vs-rest counts and rates per class; AUCs only with probabilities and both outcomes present."""
    total = int(cm.sum())
    out: dict[str, dict] = {}
    for i, c in enumerate(classes):
        tp = int(cm[i, i])
        fn = int(cm[i].sum() - tp)
        fp = int(cm[:, i].sum() - tp)
        tn = total - tp - fn - fp
        precision, recall = _div(tp, tp + fp), _div(tp, tp + fn)
        positives = y_true == c
        roc = pr = None
        if proba is not None and 0 < positives.sum() < len(y_true):
            roc = float(roc_auc_score(positives, proba[:, i]))
            pr = float(average_precision_score(positives, proba[:, i]))
        out[c] = {
            "TP": tp, "FP": fp, "FN": fn, "TN": tn, "support": tp + fn,
            "precision": precision, "recall": recall, "specificity": _div(tn, tn + fp),
            "f1": _f1(precision, recall), "fpr": _div(fp, fp + tn), "fnr": _div(fn, fn + tp),
            "roc_auc": roc, "pr_auc": pr,
        }
    return out


def brier_multiclass(y_true: np.ndarray, proba: np.ndarray, classes: list[str]) -> float:
    """Mean over rows of the squared distance between the probability vector and the one-hot truth (0 is perfect, 2 is worst)."""
    onehot = (np.asarray(y_true)[:, None] == np.asarray(classes)[None, :]).astype(float)
    return float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))


def ece(y_true: np.ndarray, proba: np.ndarray, classes: list[str], bins: int = ECE_BINS) -> tuple[float, list[dict]]:
    """Expected calibration error of the top-label confidence, equal-width bins; also returns the bin table."""
    conf = proba.max(axis=1)
    correct = np.asarray(classes)[proba.argmax(axis=1)] == np.asarray(y_true)
    edges = np.linspace(0.0, 1.0, bins + 1)
    which = np.clip(np.digitize(conf, edges[1:-1], right=True), 0, bins - 1)
    total, table = 0.0, []
    for b in range(bins):
        mask = which == b
        n = int(mask.sum())
        if n:
            acc, avg_conf = float(correct[mask].mean()), float(conf[mask].mean())
            total += n / len(conf) * abs(acc - avg_conf)
        else:
            acc = avg_conf = None
        table.append({"low": float(edges[b]), "high": float(edges[b + 1]), "count": n, "accuracy": acc, "confidence": avg_conf})
    return float(total), table


def bootstrap(
    y_true: np.ndarray, y_pred: np.ndarray, classes: list[str], groups: np.ndarray | None = None,
    n: int = N_BOOT, seed: int = SEED, alpha: float = 0.05,
) -> dict[str, dict[str, float | None]]:
    """Percentile CIs for accuracy, balanced accuracy and macro-F1, resampling cases (or rows if no groups)."""
    units = np.asarray(groups) if groups is not None else np.arange(len(y_true))
    unique = np.unique(units)
    # One confusion matrix per unit; a resample is the sum of the picked units' matrices.
    per_unit = np.stack([confusion(y_true[units == u], y_pred[units == u], classes) for u in unique])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(unique), size=(n, len(unique)))
    scores = np.array([[np.nan if v is None else v for v in _cm_scores(per_unit[d].sum(axis=0))] for d in draws])
    point = _cm_scores(per_unit.sum(axis=0))
    out = {}
    for j, name in enumerate(["accuracy", "balanced_accuracy", "macro_f1"]):
        col = scores[:, j][~np.isnan(scores[:, j])]
        low, high = (np.quantile(col, [alpha / 2, 1 - alpha / 2]) if col.size else (None, None))
        out[name] = {"point": point[j], "low": None if low is None else float(low), "high": None if high is None else float(high)}
    out["unit"] = {"resampled": "cases" if groups is not None else "rows", "n_units": int(len(unique)), "n_resamples": n, "seed": seed}
    return out


def evaluate(
    y_true: Any, y_pred: Any, y_proba: np.ndarray | None, classes: list[str],
    groups: Any = None, n_boot: int = N_BOOT, seed: int = SEED,
) -> dict[str, Any]:
    """All metrics for one model. y_proba columns must follow `classes`; pass None for models without probabilities."""
    y_true = np.asarray(y_true).astype(str)
    y_pred = np.asarray(y_pred).astype(str)
    classes = [str(c) for c in classes]
    proba = None if y_proba is None else np.asarray(y_proba, dtype=float)
    if proba is not None and proba.shape != (len(y_true), len(classes)):
        raise ValueError(f"y_proba shape {proba.shape} != ({len(y_true)}, {len(classes)})")
    unknown = set(y_true) - set(classes)
    if unknown:
        raise ValueError(f"y_true has classes not in `classes`: {sorted(unknown)}")

    cm = confusion(y_true, y_pred, classes)
    pc = per_class(cm, classes, y_true, proba)
    present = [c for c in classes if pc[c]["support"] > 0]
    support = np.array([pc[c]["support"] for c in present], dtype=float)

    def avg(key: str, weighted: bool = False) -> float | None:
        # Undefined precision (class never predicted) counts as 0 in the averages, as sklearn does with zero_division=0.
        vals = np.array([pc[c][key] if pc[c][key] is not None else 0.0 for c in present])
        if not len(vals):
            return None
        return float(np.average(vals, weights=support) if weighted else vals.mean())

    micro = precision_recall_fscore_support(y_true, y_pred, labels=classes, average="micro", zero_division=0)
    overall: dict[str, Any] = {
        "n": int(len(y_true)),
        "accuracy": float((y_true == y_pred).mean()) if len(y_true) else None,
        "balanced_accuracy": _mean([pc[c]["recall"] for c in present]),
        "macro_precision": avg("precision"), "macro_recall": avg("recall"), "macro_f1": avg("f1"),
        "weighted_precision": avg("precision", True), "weighted_recall": avg("recall", True), "weighted_f1": avg("f1", True),
        "micro_precision": float(micro[0]), "micro_recall": float(micro[1]), "micro_f1": float(micro[2]),
        "mcc": float(matthews_corrcoef(y_true, y_pred)),
        "cohen_kappa": float(cohen_kappa_score(y_true, y_pred, labels=classes)),
        "top2_accuracy": None, "log_loss": None, "brier": None, "ece": None,
    }
    reliability = None
    if proba is not None:
        top2 = np.argsort(-proba, axis=1)[:, :2]
        truth = np.array([classes.index(t) for t in y_true])
        overall["top2_accuracy"] = float((top2 == truth[:, None]).any(axis=1).mean())
        overall["log_loss"] = float(log_loss(y_true, np.clip(proba, 1e-15, 1.0), labels=classes))
        overall["brier"] = brier_multiclass(y_true, proba, classes)
        overall["ece"], reliability = ece(y_true, proba, classes)

    row_sums = cm.sum(axis=1, keepdims=True)
    normalised = [[float(v) / s if s else None for v in row] for row, s in zip(cm, row_sums[:, 0])]
    pairs = [
        {"true": classes[i], "predicted": classes[j], "count": int(cm[i, j]), "share_of_true_class": _div(cm[i, j], row_sums[i, 0])}
        for i in range(len(classes)) for j in range(len(classes)) if i != j and cm[i, j] > 0
    ]
    pairs.sort(key=lambda p: (-p["count"], p["true"], p["predicted"]))

    no_pred = [c for c in classes if pc[c]["TP"] + pc[c]["FP"] == 0]
    no_support = [c for c in classes if pc[c]["support"] == 0]
    if no_pred or no_support:
        logger.info("classes never predicted: %s; classes with zero support: %s", no_pred, no_support)
    return {
        "classes": classes,
        "per_class": pc,
        "overall": overall,
        "confusion": {"counts": cm.tolist(), "row_normalised": normalised},
        "most_confused": pairs[:TOP_CONFUSED],
        "bootstrap_95ci": bootstrap(y_true, y_pred, classes, None if groups is None else np.asarray(groups), n_boot, seed),
        "reliability": reliability,
        "has_probabilities": proba is not None,
        "notes": {"never_predicted": no_pred, "zero_support": no_support},
    }

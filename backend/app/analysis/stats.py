"""Statistics for the evaluation report: Brier score, bootstrap intervals, McNemar test, risk-coverage.

Pure functions: lists or numpy arrays in, floats or dicts out. numpy and the standard library only.
Also: ece (expected calibration error) and bootstrap_stat (interval for any statistic, e.g. macro-F1).
"""
import math

import numpy as np


def _as_arrays(confidence, correct) -> tuple[np.ndarray, np.ndarray]:
    """Turn two equal-length inputs into float and bool arrays, or raise ValueError."""
    conf = np.asarray(confidence, dtype=float)
    ok = np.asarray(correct, dtype=bool)
    if conf.shape != ok.shape or conf.ndim != 1:
        raise ValueError("confidence and correct must be 1-D and the same length")
    if conf.size == 0:
        raise ValueError("need at least one value")
    return conf, ok


def brier(confidence, correct) -> float:
    """Top-label Brier score: mean of (confidence - 1 if right else 0) squared; 0 is perfect.

    The app stores only the probability of its top answer, so this scores that answer
    (was the model right, and how sure was it), not the full one-vs-rest probability vector.
    """
    conf, ok = _as_arrays(confidence, correct)
    return float(np.mean((conf - ok.astype(float)) ** 2))


def bootstrap_ci(values, n: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """Mean of values with a percentile bootstrap interval: (point, low, high)."""
    vals = np.asarray(values, dtype=float)
    if vals.ndim != 1 or vals.size == 0:
        raise ValueError("values must be a non-empty 1-D list")
    rng = np.random.default_rng(seed)
    # Each row is one resample: pick len(vals) items with replacement, then take its mean.
    idx = rng.integers(0, vals.size, size=(n, vals.size))
    means = vals[idx].mean(axis=1)
    low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(vals.mean()), float(low), float(high)


def ece(confidence, correct, bins: int = 10) -> float:
    """Expected calibration error: how far stated confidence is from actual accuracy; 0 is perfect.

    Items go into equal-width confidence bins (0-0.1], (0.1-0.2], ... (0.9-1]; a confidence of 0 goes
    in the first bin. ECE = sum over bins of (share of items in the bin) * |accuracy - mean confidence|.
    """
    conf, ok = _as_arrays(confidence, correct)
    edges = np.linspace(0.0, 1.0, bins + 1)
    # right=True: a value equal to an edge belongs to the bin that ends at that edge
    idx = np.digitize(conf, edges[1:-1], right=True)
    total = 0.0
    for b in np.unique(idx):
        in_bin = idx == b
        total += in_bin.mean() * abs(ok[in_bin].mean() - conf[in_bin].mean())
    return float(total)


def bootstrap_stat(stat, *arrays, n: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """Any statistic with a percentile bootstrap interval: (point, low, high).

    Use it when the number is not a plain mean (macro-F1, ECE). Each resample draws the same item
    positions from every array, so pairs (true label, prediction) stay together.
    stat(*arrays) must return a float. With stat = np.mean it matches bootstrap_ci exactly.
    """
    arrs = [np.asarray(a) for a in arrays]
    if not arrs or arrs[0].ndim != 1 or arrs[0].size == 0:
        raise ValueError("need at least one non-empty 1-D array")
    size = arrs[0].size
    if any(a.shape != (size,) for a in arrs):
        raise ValueError("all arrays must be 1-D and the same length")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, size, size=(n, size))  # same draws as bootstrap_ci
    values = np.array([stat(*(a[row] for a in arrs)) for row in idx], dtype=float)
    low, high = np.quantile(values, [alpha / 2, 1 - alpha / 2])
    return float(stat(*arrs)), float(low), float(high)


def mcnemar(a_correct, b_correct) -> dict:
    """McNemar test on paired results of models A and B over the same items.

    b = A right and B wrong; c = A wrong and B right. Exact two-sided binomial test when
    b + c < 25, otherwise chi-square with continuity correction (1 degree of freedom).
    """
    a = np.asarray(a_correct, dtype=bool)
    m = np.asarray(b_correct, dtype=bool)
    if a.shape != m.shape or a.ndim != 1:
        raise ValueError("a_correct and b_correct must be 1-D and the same length")
    b = int(np.sum(a & ~m))
    c = int(np.sum(~a & m))
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "n": 0, "statistic": 0.0, "p_value": 1.0, "method": "no_disagreements"}
    if n < 25:
        # Under "no difference", each disagreement is a fair coin flip: P(k or fewer of the rarer side), doubled.
        tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
        return {"b": b, "c": c, "n": n, "statistic": float(min(b, c)),
                "p_value": min(1.0, 2 * tail), "method": "exact_binomial"}
    stat = (abs(b - c) - 1) ** 2 / n
    # Chi-square with 1 degree of freedom: P(X > stat) = erfc(sqrt(stat / 2)).
    return {"b": b, "c": c, "n": n, "statistic": float(stat),
            "p_value": float(math.erfc(math.sqrt(stat / 2))), "method": "chi2_continuity"}


def risk_coverage(confidence, correct) -> list[dict]:
    """Accuracy against share answered: one row per distinct confidence used as the cut-off, high to low."""
    conf, ok = _as_arrays(confidence, correct)
    total = conf.size
    rows = []
    for t in np.unique(conf)[::-1]:
        answered = conf >= t
        k = int(answered.sum())
        acc = float(ok[answered].mean())
        rows.append({"threshold": float(t), "answered": k, "coverage": k / total,
                     "accuracy": acc, "risk": 1 - acc})
    return rows

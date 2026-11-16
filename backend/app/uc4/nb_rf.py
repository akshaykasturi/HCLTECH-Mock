"""Two UC4 cause classifiers on the shared TF-IDF features: Complement Naive Bayes and Random Forest.

Both are CalibratedCauseClassifier (classifier.py): sigmoid calibration on case-grouped folds of train.
- ComplementNB: word-count style model; needs features >= 0, so it uses build_features("nb").
- RandomForest: many decision trees voting; random_state=42 so the same data gives the same trees.
"""
from functools import partial

from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import ComplementNB

from app.analysis.stats import brier
from app.uc4.classifier import CalibratedCauseClassifier
from app.uc4.evaluate_classifier import macro_f1
from app.uc4.ml.cause_data import CauseSplit
from app.uc4.ml.features import build_features

# Grids, listed simplest first: on a tie, the earlier setting wins.
NB_GRID = [{"alpha": a} for a in (1.0, 0.3, 0.1, 0.01)]  # more smoothing = simpler
RF_GRID = [{"n_estimators": n, "max_depth": d} for n in (100, 300) for d in (10, 30, None)]


def complement_nb(alpha: float = 1.0) -> CalibratedCauseClassifier:
    """ComplementNB(alpha) on TF-IDF; alpha = smoothing for words a cause never used in train."""
    return CalibratedCauseClassifier("complement_nb", "tfidf", partial(build_features, "nb"),
                                     ComplementNB(alpha=alpha), params={"alpha": alpha})


def random_forest(n_estimators: int = 100, max_depth: int | None = None) -> CalibratedCauseClassifier:
    """RandomForestClassifier on TF-IDF; max_depth=None lets trees grow until leaves are pure."""
    clf = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, random_state=42, n_jobs=1)
    return CalibratedCauseClassifier("random_forest", "tfidf", build_features, clf,
                                     params={"n_estimators": n_estimators, "max_depth": max_depth})


MODELS = {"complement_nb": (complement_nb, NB_GRID), "random_forest": (random_forest, RF_GRID)}


def tune(build, grid: list[dict], train: CauseSplit, validation: CauseSplit) -> tuple[CalibratedCauseClassifier, list[dict]]:
    """Fit every grid setting on train, score it on validation focal rows; return (best fitted model, all rows).

    Best = highest macro-F1, then lowest Brier, then the earliest (simplest) setting.
    Takes only train and validation: the test split is never seen here.
    """
    focal = validation.focal().labelled()
    rows, best, best_key = [], None, None
    for i, params in enumerate(grid):
        model = build(**params).fit(train.X, train.y, groups=train.case_id)
        labels, top, _ = model.predict(focal.X)
        f1 = macro_f1(focal.y.astype(str), labels)
        b = brier(top, focal.y == labels)
        rows.append({"params": params, "macro_f1": f1, "brier": b})
        key = (-f1, b, i)
        if best_key is None or key < best_key:
            best, best_key = model, key
    return best, rows

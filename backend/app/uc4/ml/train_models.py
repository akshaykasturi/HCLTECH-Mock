"""Train the UC4 failure-class models on the shared features: a status-code rules baseline, then
Logistic Regression, LinearSVC (sigmoid-calibrated on the validation split) and Random Forest,
each on TF-IDF and on embedding features.

Tuning uses the train split only, with folds grouped by case (rows of one case are near-copies).
The test split is never touched here. Fitted models go to backend/models/uc4/ (git-ignored).
"""
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from app.uc4.ml.embed_features import build_embed_features
from app.uc4.ml.features import (
    build_features,
    get_group_split,
    get_group_templates,
    get_groups,
    get_split,
    get_validation,
)

logger = logging.getLogger(__name__)

SEED = 42
MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "uc4"  # backend/models/ is git-ignored; one subfolder per split mode
FEATURE_SETS: dict[str, Callable[[], ColumnTransformer]] = {
    "tfidf": lambda: build_features("default"),
    "embeddings": build_embed_features,
}
# Model name -> (estimator, grid). Grids from the team brief; class_weight="balanced" for uneven classes.
MODELS: dict[str, tuple[Callable[[], BaseEstimator], dict[str, list[Any]]]] = {
    "lr": (lambda: LogisticRegression(class_weight="balanced", max_iter=2000), {"clf__C": [0.1, 1, 10]}),
    "linear_svc": (lambda: LinearSVC(class_weight="balanced", random_state=SEED), {"clf__C": [0.1, 1, 10]}),
    "rf": (
        lambda: RandomForestClassifier(class_weight="balanced", random_state=SEED, n_jobs=1),
        {"clf__n_estimators": [200, 500], "clf__max_depth": [None, 20]},
    ),
}
# Simpler first: used to break statistical ties when recommending a model.
SIMPLICITY = ["rules", "lr", "linear_svc", "rf"]


class RulesBaseline(BaseEstimator, ClassifierMixin):
    """Predict the class each HTTP status had most often in train; unseen status -> most common class.

    Learned from data, not hand-written, so it holds no hardcoded rules. No probabilities.
    """

    def __init__(self, column: str = "status") -> None:
        self.column = column

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RulesBaseline":
        """Learn the status -> majority class table."""
        frame = pd.DataFrame({"key": X[self.column].astype(str).to_numpy(), "y": np.asarray(y)})
        self.classes_ = np.array(sorted(frame["y"].unique()))
        self.default_ = frame["y"].value_counts().sort_index().idxmax()
        # Ties broken alphabetically so the table never depends on row order.
        counts = frame.groupby(["key", "y"]).size().reset_index(name="n").sort_values(["key", "n", "y"], ascending=[True, False, True])
        self.table_ = dict(counts.drop_duplicates("key")[["key", "y"]].itertuples(index=False, name=None))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Look up each row's status; fall back to the most common class."""
        return np.array([self.table_.get(str(k), self.default_) for k in X[self.column]])


def n_folds(groups: pd.Series, y: pd.Series, wanted: int = 5) -> int:
    """Largest fold count <= wanted that every class can fill with at least one case."""
    cases_per_class = pd.DataFrame({"g": groups.to_numpy(), "y": y.to_numpy()}).groupby("y")["g"].nunique()
    k = int(min(wanted, cases_per_class.min()))
    if k < wanted:
        logger.warning("smallest class has %d cases; using %d folds instead of %d", cases_per_class.min(), k, wanted)
    if k < 2:
        raise ValueError("need at least 2 cases per class for cross-validation")
    return k


def template_folds(groups: pd.Series, y: pd.Series, wanted: int = 5) -> int:
    """Fold count for grouped mode: min(wanted, templates in the smallest class), at least 2."""
    per_class = pd.DataFrame({"g": groups.to_numpy(), "y": y.to_numpy()}).groupby("y")["g"].nunique()
    k = max(2, int(min(wanted, per_class.min())))
    logger.info("grouped CV: smallest class has %d templates in train -> %d template-grouped folds", per_class.min(), k)
    return k


def make_cv(split: str, groups: pd.Series, y: pd.Series) -> StratifiedGroupKFold:
    """Folds that never split a group: cases (random mode) or message templates (grouped mode).

    Grouped mode uses StratifiedGroupKFold rather than plain GroupKFold: with only 2 templates in the
    smallest classes, plain GroupKFold left whole classes out of a fold's training part (checked), which
    made the CV scores meaningless. StratifiedGroupKFold still keeps every template inside one fold.
    """
    k = template_folds(groups, y) if split == "grouped" else n_folds(groups, y)
    return StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=SEED)


def train_one(
    feature_set: str, model_name: str, X: pd.DataFrame, y: pd.Series, groups: pd.Series, split: str = "random"
) -> tuple[Pipeline, dict[str, Any]]:
    """Grid-search one feature set + model on train (grouped folds, f1_macro); refit on all of train."""
    make_model, grid = MODELS[model_name]
    pipe = Pipeline([("features", FEATURE_SETS[feature_set]()), ("clf", make_model())])
    cv = make_cv(split, groups, y)
    search = GridSearchCV(pipe, grid, scoring="f1_macro", cv=cv, n_jobs=1, refit=True)
    start = time.perf_counter()
    search.fit(X, y, groups=groups)
    seconds = time.perf_counter() - start
    info = {
        "best_params": search.best_params_,
        "cv_f1_macro": float(search.best_score_),
        "cv_folds": cv.get_n_splits(),
        "cv_kind": type(cv).__name__,
        "fit_seconds": seconds,  # whole grid search, including the final refit
    }
    logger.info("%s/%s: cv f1_macro %.3f with %s (%.1fs)", feature_set, model_name, search.best_score_, search.best_params_, seconds)
    return search.best_estimator_, info


def calibrate(model: Pipeline, X_val: pd.DataFrame, y_val: pd.Series) -> CalibratedClassifierCV:
    """Sigmoid calibration of a fitted model on the validation split (the model itself is frozen)."""
    return CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid").fit(X_val, y_val)


def calibrate_cv(model: Pipeline, X: pd.DataFrame, y: pd.Series, groups: pd.Series, n_splits: int) -> CalibratedClassifierCV:
    """Sigmoid calibration by grouped cross-validation on train (grouped mode has no separate validation set)."""
    folds = list(StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=SEED).split(X, y, groups))
    return CalibratedClassifierCV(clone(model), method="sigmoid", cv=folds).fit(X, y)


def split_data(split: str) -> dict[str, Any]:
    """Training data for a split mode: X/y train, groups for CV, and validation data (random mode only)."""
    if split == "grouped":
        X_train, _, y_train, _ = get_group_split()
        return {"X": X_train, "y": y_train, "groups": get_group_templates(X_train.index), "X_val": None, "y_val": None}
    if split == "random":
        X_train, _, y_train, _ = get_split()
        X_val, y_val = get_validation()
        return {"X": X_train, "y": y_train, "groups": get_groups("train"), "X_val": X_val, "y_val": y_val}
    raise ValueError(f"split must be 'random' or 'grouped', got {split!r}")


def fit_all(data: dict[str, Any], feature_sets: list[str], split: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fit the baseline and every model on `data`; returns (bundles, summary) without saving anything."""
    X_train, y_train, groups = data["X"], data["y"], data["groups"]
    classes = sorted(y_train.unique())
    bundles: dict[str, dict[str, Any]] = {}
    summary: dict[str, dict[str, Any]] = {}
    start = time.perf_counter()
    rules = RulesBaseline().fit(X_train, y_train)
    summary["rules"] = {"fit_seconds": time.perf_counter() - start, "table": rules.table_}
    bundles["rules"] = {"model": rules, "calibrated": None, "classes": classes}
    for fs in feature_sets:
        for name in MODELS:
            model, info = train_one(fs, name, X_train, y_train, groups, split)
            calibrated = None
            if name == "linear_svc":  # LinearSVC has no predict_proba: calibrate for probability metrics
                if split == "grouped":
                    calibrated = calibrate_cv(model, X_train, y_train, groups, info["cv_folds"])
                    info["calibrated_on"] = f"grouped {info['cv_folds']}-fold CV on train"
                else:
                    calibrated = calibrate(model, data["X_val"], data["y_val"])
                    info["calibrated_on"] = "validation"
            if list(model.classes_) != classes:
                raise RuntimeError(f"{fs}/{name} class order {list(model.classes_)} != {classes}")
            bundles[f"{fs}/{name}"] = {"model": model, "calibrated": calibrated, "classes": classes}
            summary[f"{fs}/{name}"] = info
    return bundles, summary


def train_all(feature_sets: list[str], split: str = "random", model_dir: Path = MODEL_DIR) -> dict[str, dict[str, Any]]:
    """Train the baseline and every model for a split mode; save each with joblib plus a JSON summary."""
    out_dir = model_dir / split
    out_dir.mkdir(parents=True, exist_ok=True)
    bundles, summary = fit_all(split_data(split), feature_sets, split)
    for key, bundle in bundles.items():
        joblib.dump(bundle, out_dir / f"{key.replace('/', '__')}.joblib")
    (out_dir / "training_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("saved %d models to %s", len(bundles), out_dir)
    return summary


def load_models(feature_sets: list[str], split: str = "random", model_dir: Path = MODEL_DIR) -> dict[str, dict[str, Any]]:
    """Load saved models of a split mode: {"rules": {...}, "tfidf/lr": {...}, ...}, each with model, calibrated, classes."""
    out: dict[str, dict[str, Any]] = {}
    folder = model_dir / split
    rules = folder / "rules.joblib"
    if rules.exists():
        out["rules"] = joblib.load(rules)
    for fs in feature_sets:
        for name in MODELS:
            path = folder / f"{fs}__{name}.joblib"
            if path.exists():
                out[f"{fs}/{name}"] = joblib.load(path)
            else:
                logger.warning("model not found: %s (run scripts/train_models.py --split %s)", path, split)
    return out

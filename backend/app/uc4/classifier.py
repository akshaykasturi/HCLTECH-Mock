"""Shared interface for the UC4 cause classifiers (NB, RF, LR, LinearSVC): same calls, comparable outputs.

Every model has a model_name, a feature_set name, fit(X, y, groups) and
predict(X) -> (labels, top_probabilities, all_probabilities), with columns of all_probabilities in classes_ order.

CalibratedCauseClassifier is the ready-made version: features + classifier in one pipeline, wrapped in
CalibratedClassifierCV with case-grouped folds. Each fold fits on 2/3 of the train cases and learns the
calibration on the other 1/3, so rows from one case never sit on both sides. The 3 fold models are averaged.
"""
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import numpy as np
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline


class CauseClassifier(ABC):
    """What every UC4 cause classifier offers."""

    model_name: str  # e.g. "complement_nb"
    feature_set: str  # e.g. "tfidf" or "embeddings"
    classes_: np.ndarray  # cause names, the column order of all_probabilities

    @abstractmethod
    def fit(self, X: Any, y: Any, groups: Any = None) -> "CauseClassifier":
        """Learn from train rows only. groups = case_id per row (needed for case-grouped calibration)."""

    @abstractmethod
    def predict_proba(self, X: Any) -> np.ndarray:
        """(n_rows, n_classes) probabilities; each row sums to 1."""

    def predict(self, X: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(labels, top_probabilities, all_probabilities): the most likely cause, its probability, all of them."""
        probs = self.predict_proba(X)
        best = probs.argmax(axis=1)
        return self.classes_[best], probs[np.arange(len(best)), best], probs


def grouped_folds(y: Any, groups: Any, n_folds: int = 3) -> list[tuple[np.ndarray, np.ndarray]]:
    """(fit rows, calibration rows) per fold: whole cases only, each cause spread over the folds.

    Raises if a fold's fit part misses a cause, since that cause could then never be predicted.
    """
    y, groups = np.asarray(y), np.asarray(groups)
    folds = list(StratifiedGroupKFold(n_splits=n_folds).split(np.zeros(len(y)), y, groups))
    for fit_rows, _ in folds:
        missing = set(y) - set(y[fit_rows])
        if missing:
            raise ValueError(f"a fit fold has no rows for {sorted(missing)}; use fewer folds")
    return folds


class CalibratedCauseClassifier(CauseClassifier):
    """Pipeline(features, classifier) inside CalibratedClassifierCV with case-grouped folds."""

    def __init__(self, model_name: str, feature_set: str, make_features: Callable[[], Any], classifier: Any,
                 params: dict | None = None, method: str = "sigmoid", n_folds: int = 3) -> None:
        self.model_name = model_name
        self.feature_set = feature_set
        self.make_features = make_features  # returns a NEW unfitted feature transformer
        self.classifier = classifier
        self.params = params or {}  # the hyperparameters, for reports
        self.method = method
        self.n_folds = n_folds

    def fit(self, X: Any, y: Any, groups: Any = None) -> "CalibratedCauseClassifier":
        """Fit on train rows; groups (case_id) is required."""
        if groups is None:
            raise ValueError("groups (case_id per row) is required for case-grouped calibration")
        y = np.asarray(y, dtype=str)
        pipe = Pipeline([("features", self.make_features()), ("clf", clone(self.classifier))])
        self.folds_ = grouped_folds(y, groups, self.n_folds)
        self.model_ = CalibratedClassifierCV(pipe, method=self.method, cv=self.folds_).fit(X, y)
        self.classes_ = self.model_.classes_
        return self

    def predict_proba(self, X: Any) -> np.ndarray:
        return self.model_.predict_proba(X)

    def describe(self) -> str:
        """e.g. 'complement_nb (tfidf) alpha=0.1'."""
        settings = " ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.model_name} ({self.feature_set}) {settings}".strip()

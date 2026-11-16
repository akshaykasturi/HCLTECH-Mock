"""Simple baselines for the evaluation report. For comparison only: the app never uses them.

A model is only worth reporting if it beats these:
  - majority_baseline: always say the most common label (the "do nothing smart" floor);
  - text_only_baseline: TF-IDF on the error message alone + logistic regression (what words alone get you).

Rows come from the team's shared pipeline (app/uc4/ml/features.py: get_split, get_validation, get_groups),
so a baseline sees exactly the same rows as the real classifiers.
"""
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from app.uc4.ml.features import EVAL_DIR, get_groups, get_split, get_validation

Level = Literal["class", "cause"]


def majority_baseline(y_train, n: int) -> list:
    """Predict the most common training label n times (ties: alphabetically first). The floor any model must beat."""
    counts = Counter(y_train)
    if not counts:
        raise ValueError("y_train is empty")
    best = max(counts.values())
    label = min(k for k, v in counts.items() if v == best)
    return [label] * n


def text_tfidf() -> FeatureUnion:
    """Unfitted TF-IDF used by the text-only baseline (Akhilesh's settings): word 1-2 grams + char 3-5 grams."""
    return FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True)),
    ])


@lru_cache(maxsize=1)
def _causes() -> dict[str, Optional[str]]:
    with open(EVAL_DIR / "cases.jsonl", encoding="utf-8") as f:
        return {c["case_id"]: c["expected_cause"] for c in (json.loads(line) for line in f if line.strip())}


def baseline_rows(split: Literal["train", "validation", "test"]) -> pd.DataFrame:
    """Rows of one split from the shared pipeline: case_id, text (cleaned message), class, cause, insufficient.

    Insufficient-evidence cases (expected_cause is null) are flagged here; text_only_baseline leaves them
    out of training and keeps them, flagged, in validation and test.
    """
    if split == "validation":
        X, y = get_validation()
    else:
        X_train, X_test, y_train, y_test = get_split()
        X, y = (X_train, y_train) if split == "train" else (X_test, y_test)
    groups = get_groups(split)
    causes = _causes()
    frame = pd.DataFrame({
        "case_id": groups.to_numpy(),
        "text": X["message"].to_numpy(),
        "class": y.to_numpy(),
        "cause": [causes[c] for c in groups],
    })
    frame["insufficient"] = frame["cause"].isna()
    return frame


@dataclass
class BaselineResult:
    """Test-split output of a baseline. Score only rows where insufficient is False."""

    level: Level
    case_ids: list[str]
    y_true: list[Optional[str]]  # None for insufficient rows at cause level
    insufficient: np.ndarray  # bool per row
    predictions: np.ndarray
    probabilities: np.ndarray  # shape (rows, len(classes))
    classes: list[str]
    model: Pipeline

    def accuracy(self) -> float:
        """Accuracy on the labelled (not insufficient) test rows."""
        keep = ~self.insufficient
        truth = np.array(self.y_true, dtype=object)[keep]
        return float(np.mean(self.predictions[keep] == truth))


def text_only_baseline(level: Level = "class") -> BaselineResult:
    """TF-IDF on the error message only + LogisticRegression, fitted on TRAIN only; predicts the TEST split.

    level="class" predicts the failure class, level="cause" the cause. Insufficient-evidence cases are left
    out of training (they have no cause to learn) and kept but flagged in the test output.
    """
    if level not in ("class", "cause"):
        raise ValueError(f"level must be 'class' or 'cause', got {level!r}")
    train = baseline_rows("train")
    train = train[~train["insufficient"]]
    test = baseline_rows("test")

    model = Pipeline([("tfidf", text_tfidf()), ("clf", LogisticRegression(max_iter=2000))])
    model.fit(train["text"].tolist(), train[level].tolist())
    texts = test["text"].tolist()
    y_true = [None if pd.isna(v) else v for v in test[level]]
    return BaselineResult(
        level=level, case_ids=test["case_id"].tolist(), y_true=y_true,
        insufficient=test["insufficient"].to_numpy(), predictions=model.predict(texts),
        probabilities=model.predict_proba(texts), classes=[str(c) for c in model.classes_], model=model,
    )

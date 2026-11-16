"""Rows for the UC4 cause classifiers: the shared cleaned feature columns plus the cause target.

Features come from features.load_dataset (secrets already masked by clean_text). This file only adds:
- the target: expected_cause from cases.jsonl (not the class label in the CSV);
- insufficient-evidence cases (expected_cause is null): left out of train, because they have no cause
  to learn; kept in validation and test with insufficient=True so the evaluation can score CLARIFY;
- is_focal and case_id, so the evaluation can score one row per case.
"""
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from app.uc4.ml.features import CONFIG, EVAL_DIR, load_dataset
from app.uc4.store import load_cases

SPLITS = ("train", "validation", "test")


@dataclass
class CauseSplit:
    """One split, row-aligned: X[i] is log line i, y[i] its cause, case_id[i] its case."""

    X: pd.DataFrame  # cleaned feature columns, one row per failing log line
    y: np.ndarray  # expected_cause per row; None for insufficient cases
    case_id: np.ndarray
    is_focal: np.ndarray  # True for the one focal line of each case
    insufficient: np.ndarray  # True when the case has no cause (CLARIFY)

    def __len__(self) -> int:
        return len(self.y)

    def take(self, mask: np.ndarray) -> "CauseSplit":
        """The rows where mask is True."""
        return CauseSplit(self.X[mask].reset_index(drop=True), self.y[mask], self.case_id[mask],
                          self.is_focal[mask], self.insufficient[mask])

    def focal(self) -> "CauseSplit":
        """One row per case: the focal line."""
        return self.take(self.is_focal)

    def labelled(self) -> "CauseSplit":
        """Rows of cases that have a cause."""
        return self.take(~self.insufficient)


def load_cause_split(split: Literal["train", "validation", "test"]) -> CauseSplit:
    """Load one split; train never contains insufficient cases."""
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, not {split!r}")
    X, _ = load_dataset(split)
    flags = pd.read_csv(EVAL_DIR / CONFIG["files"][split], usecols=["case_id", "is_focal"], dtype=str)
    if len(flags) != len(X):
        raise RuntimeError(f"{split}: feature rows and CSV rows differ")
    cases = load_cases()
    case_id = flags["case_id"].to_numpy(dtype=object)
    y = np.array([cases[c].expected_cause for c in case_id], dtype=object)
    data = CauseSplit(X, y, case_id, (flags["is_focal"] == "True").to_numpy(),
                      np.array([v is None for v in y], dtype=bool))
    return data.labelled() if split == "train" else data

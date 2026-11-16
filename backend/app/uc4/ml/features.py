"""Shared feature extraction for the UC4 failure-class classifiers (TF-IDF + encoding).

Every classifier (SVM, Naive Bayes, Logistic Regression, Random Forest) uses the same
cleaning, the same columns and the same train/test rows, so their scores can be compared.
No classifier lives here: plug one in with Pipeline([("features", build_features()), ("clf", model)]).
"""
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, MinMaxScaler, OneHotEncoder, StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config: change columns or files here, no code change needed below.
# ---------------------------------------------------------------------------
EVAL_DIR = Path(__file__).resolve().parents[3] / "data" / "eval" / "uc4"

CONFIG: dict[str, Any] = {
    # The generator's case-grouped splits: no case (and so no duplicated log line) spans two splits.
    # "calibration" is the repo's validation split (tuning only).
    "files": {
        "train": "classifier_train.csv",
        "validation": "classifier_calibration.csv",
        "test": "classifier_test.csv",
    },
    "label": "label",
    "group": "case_id",  # used only to keep cases together (GroupKFold); never a feature
    # Never given to a model: the answer, the case ID, and a sampling flag.
    "exclude": ["label", "case_id", "is_focal"],
    "text": "message",  # one free-text column, fed to both TF-IDF vectorizers
    "categorical": ["status", "route", "error_code", "upstream_error"],
    "numeric": ["ratelimit_remaining"],
    "numeric_log1p": ["db_pool_waiting"],  # skewed counts: log1p before scaling
    "boolean": [
        "has_www_authenticate",
        "has_retry_after",
        "has_ratelimit_remaining",
        "has_db_pool_waiting",
    ],
    "missing": "none",  # category used when a field is absent
}

# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------
# Order matters: secrets first (they can contain hex, numbers and dots), then IDs, then numbers.
_SUBS: list[tuple[re.Pattern[str], str]] = [
    # Only credential-looking values (8+ chars with a digit or dot), so "Bearer token expired" keeps its words.
    (re.compile(r"\bBearer\s+(?=[A-Za-z0-9\-_~+/]*[\d.])[A-Za-z0-9\-._~+/]{8,}=*", re.I), "bearer <TOKEN>"),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]*"), "<JWT>"),
    (re.compile(r"\b(?:nvp_(?:live|test)_\w+|sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16})\b"), "<API_KEY>"),
    (
        re.compile(r"\b(api[_-]?key|access[_-]?token|secret|password|passwd)(\s*[=:]\s*)\S+", re.I),
        r"\1\2<SECRET>",
    ),
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "<EMAIL>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<UUID>"),
    (re.compile(r"\bc-[0-9a-f]{10}\b", re.I), "<CORR_ID>"),
    (re.compile(r"\breq_[0-9a-f]{6,}\b", re.I), "<REQ_ID>"),
    (re.compile(r"\b((?:request|correlation)[_-]?id)(\s*[=:]\s*)\S+", re.I), r"\1\2<ID>"),
    (
        re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
        "<TS>",
    ),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<HEX>"),
    (re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12,}\b", re.I), "<HEX>"),
    (re.compile(r"\b\d{5,}\b"), "<NUM>"),
]
_PLACEHOLDER = re.compile(r"<([a-z_]+)>")
_SPACES = re.compile(r"\s+")


def clean_text(s: str | None) -> str:
    """Mask secrets and volatile IDs with placeholders, lowercase, keep error codes intact."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    text = str(s)
    for pattern, repl in _SUBS:
        text = pattern.sub(repl, text)
    text = text.lower()
    text = _PLACEHOLDER.sub(lambda m: f"<{m.group(1).upper()}>", text)  # keep placeholders upper-case
    return _SPACES.sub(" ", text).strip()


# ---------------------------------------------------------------------------
# Parsing one flattened log line into columns
# ---------------------------------------------------------------------------
_LINE = re.compile(r"^status=(?P<status>\S+) route=(?P<route>\S+ \S+) code=(?P<code>\S+) message=(?P<msg>.*)$")
_UPSTREAM = re.compile(r"\s+upstream_error=(\S+)")
_RL_REMAINING = re.compile(r"\s+ratelimit_remaining=(\d+)")
_WAITING = re.compile(r"\bwaiting=(\d+)")


def _parse_line(line: str) -> dict[str, Any]:
    """Split one 'status=.. route=.. code=.. message=..' line into structured fields."""
    miss = CONFIG["missing"]
    m = _LINE.match(line.strip())
    if m:
        status, route, code, msg = m.group("status"), m.group("route"), m.group("code"), m.group("msg")
    else:
        status, route, code, msg = miss, miss, miss, line
    upstream = _UPSTREAM.search(msg)
    remaining = _RL_REMAINING.search(msg)
    waiting = _WAITING.search(msg)
    has_www = bool(re.search(r"\s+has_www_authenticate\b", msg))
    has_retry = bool(re.search(r"\s+has_retry_after\b", msg))
    # Remove the trailing key=value flags from the message; they become their own columns.
    for flag in (_UPSTREAM, _RL_REMAINING, re.compile(r"\s+has_www_authenticate\b"), re.compile(r"\s+has_retry_after\b")):
        msg = flag.sub("", msg)
    return {
        "status": status,
        "route": route,
        "error_code": code if code else miss,
        "upstream_error": upstream.group(1) if upstream else miss,
        "message": clean_text(msg),
        "ratelimit_remaining": float(remaining.group(1)) if remaining else np.nan,
        "db_pool_waiting": float(waiting.group(1)) if waiting else np.nan,
        "has_www_authenticate": int(has_www),
        "has_retry_after": int(has_retry),
        "has_ratelimit_remaining": int(remaining is not None),
        "has_db_pool_waiting": int(waiting is not None),
        "_parsed": m is not None,
    }


def parse_lines(lines: Iterable[str]) -> pd.DataFrame:
    """Turn raw log lines (the classifier 'text' column) into the feature columns of CONFIG."""
    rows = [_parse_line(str(line)) for line in lines]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=_feature_columns())
    unparsed = int((~frame["_parsed"]).sum())
    if unparsed:
        logger.warning("%d of %d lines did not match the expected log format; used whole line as message", unparsed, len(frame))
    return frame[_feature_columns()]


def _feature_columns() -> list[str]:
    """All model input columns, in a fixed order."""
    return (
        [CONFIG["text"]]
        + CONFIG["categorical"]
        + CONFIG["numeric"]
        + CONFIG["numeric_log1p"]
        + CONFIG["boolean"]
    )


# ---------------------------------------------------------------------------
# Feature transformer
# ---------------------------------------------------------------------------
def _log1p_nonneg(x: np.ndarray) -> np.ndarray:
    """log1p on values clipped at 0 (counts can't be negative; keeps the output finite)."""
    return np.log1p(np.clip(x, 0, None))


def build_features(mode: Literal["default", "nb"] = "default", **overrides: Any) -> ColumnTransformer:
    """Return an UNFITTED ColumnTransformer; mode "nb" keeps every feature >= 0 for MultinomialNB/ComplementNB.

    Transformer names (for GridSearchCV inside Pipeline step "features"):
    text_word, text_char, cat, num, num_log, bool, e.g. "features__text_word__ngram_range".
    `overrides` are passed to set_params, e.g. build_features(text_word__min_df=1).
    """
    if mode not in ("default", "nb"):
        raise ValueError(f"mode must be 'default' or 'nb', got {mode!r}")

    def scaler() -> StandardScaler | MinMaxScaler:
        # clip=True: test values outside the training range stay in [0, 1], so never negative.
        return StandardScaler() if mode == "default" else MinMaxScaler(clip=True)

    def impute() -> SimpleImputer:
        # Missing number (field absent in the log line) -> 0; the has_* flag says it was absent.
        return SimpleImputer(strategy="constant", fill_value=0.0)

    text_col = CONFIG["text"]
    # Text is already lower-cased by clean_text; lowercase=False keeps placeholders like <IP> distinct.
    transformers = [
        (
            "text_word",
            TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.9,
                sublinear_tf=True,
                lowercase=False,
                token_pattern=r"(?u)\b[\w\-\.]+\b",
            ),
            text_col,
        ),
        (
            "text_char",
            TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, lowercase=False),
            text_col,
        ),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CONFIG["categorical"]),
        ("num", Pipeline([("impute", impute()), ("scale", scaler())]), CONFIG["numeric"]),
        (
            "num_log",
            Pipeline(
                [
                    ("impute", impute()),
                    ("log1p", FunctionTransformer(_log1p_nonneg, feature_names_out="one-to-one")),
                    ("scale", scaler()),
                ]
            ),
            CONFIG["numeric_log1p"],
        ),
        ("bool", "passthrough", CONFIG["boolean"]),
    ]
    features = ColumnTransformer(transformers, remainder="drop")
    if overrides:
        features.set_params(**overrides)
    logger.debug("built features: mode=%s overrides=%s", mode, overrides)
    return features


# ---------------------------------------------------------------------------
# Data loading and the shared split
# ---------------------------------------------------------------------------
def _read(split: str) -> pd.DataFrame:
    """Read one classifier CSV (train, validation or test) as strings."""
    files = CONFIG["files"]
    if split not in files:
        raise ValueError(f"split must be one of {list(files)}, got {split!r}")
    return pd.read_csv(EVAL_DIR / files[split], dtype=str, keep_default_na=False)


def load_dataset(split: Literal["train", "validation", "test", "all"] = "all") -> tuple[pd.DataFrame, pd.Series]:
    """Return (X, y) for a split: cleaned feature columns, excluded columns dropped, label as y."""
    splits = list(CONFIG["files"]) if split == "all" else [split]
    raw = pd.concat([_read(s) for s in splits], ignore_index=True)
    X = parse_lines(raw["text"])
    assert not set(CONFIG["exclude"]) & set(X.columns), "an excluded column leaked into X"
    y = raw[CONFIG["label"]].rename("label")
    logger.info("loaded %s: %d rows, %d classes", split, len(X), y.nunique())
    return X, y


def get_groups(split: Literal["train", "validation", "test"] = "train") -> pd.Series:
    """Case IDs aligned row-for-row with load_dataset(split); use with GroupKFold for cross-validation."""
    return _read(split)[CONFIG["group"]].rename("case_id")


def get_split() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Return (X_train, X_test, y_train, y_test): the team's fixed case-grouped split, same rows every call."""
    X_train, y_train = load_dataset("train")
    X_test, y_test = load_dataset("test")
    overlap = set(get_groups("train")) & set(get_groups("test"))
    if overlap:
        raise RuntimeError(f"cases appear in both train and test: {sorted(overlap)[:5]}")
    return X_train, X_test, y_train, y_test


def get_validation() -> tuple[pd.DataFrame, pd.Series]:
    """Return (X_val, y_val) for tuning (thresholds, calibration). Never use the test split for this."""
    return load_dataset("validation")

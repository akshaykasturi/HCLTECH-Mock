"""Embedding-based features for the UC4 failure-class classifiers: the counterpart of features.py.

Only the text representation differs from the TF-IDF version: the cleaned message is embedded with a
pretrained sentence model (fastembed, BAAI/bge-small-en-v1.5, 384 dims, CPU). Cleaning, parsing,
columns, exclusions, the structured transformers and the train/test split are all imported from
features.py, so LR/SVM results on the two feature sets are directly comparable.
"""
import hashlib
import logging
import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer

from app.uc4.ml.features import (  # noqa: F401  (re-exported so callers need only this module)
    CONFIG,
    build_features,
    clean_text,
    get_groups,
    get_split,
    get_validation,
    load_dataset,
)

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
# Settings come from environment variables, with defaults that match the old app's embedder.
DEFAULT_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
MODEL_DIR = Path(os.getenv("EMBED_CACHE_DIR", BACKEND_DIR / ".cache" / "fastembed"))  # model files (git-ignored)
VECTOR_CACHE_DIR = BACKEND_DIR / ".cache" / "embeddings"  # cached vectors (git-ignored via backend/.cache/)
TEXT_STEPS = ("text_word", "text_char")  # the TF-IDF steps that build_embed_features replaces


@lru_cache(maxsize=4)
def _load_model(model_name: str) -> Any:
    """Load a fastembed model once per process (downloads ~65 MB to MODEL_DIR on first use)."""
    from fastembed import TextEmbedding  # imported here so tests with a fake embedder never load onnxruntime

    logger.info("loading embedding model %s from %s", model_name, MODEL_DIR)
    return TextEmbedding(model_name=model_name, cache_dir=str(MODEL_DIR))


def embed_texts(texts: list[str], model_name: str = DEFAULT_MODEL, batch_size: int = 64) -> np.ndarray:
    """Embed texts with the pretrained model; returns L2-normalised float32 rows (n, dim)."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    vectors = np.array(list(_load_model(model_name).embed(texts, batch_size=batch_size)), dtype=np.float32)
    return l2_normalise(vectors)


def l2_normalise(m: np.ndarray) -> np.ndarray:
    """Scale each row to unit length; an all-zero row stays zero instead of becoming NaN."""
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1.0, norms)


def _cache_key(model_name: str, text: str) -> str:
    """sha256 of model name + cleaned text: the same text under another model gets another key."""
    return hashlib.sha256(f"{model_name}\n{text}".encode("utf-8")).hexdigest()


class VectorCache:
    """Embeddings on disk in one .npz per model (keys + vectors), so re-runs never re-embed."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        slug = "".join(c if c.isalnum() or c in "-_." else "_" for c in model_name)
        self.path = Path(cache_dir) / f"embeddings_{slug}.npz"
        self._data: dict[str, np.ndarray] = {}
        if self.path.exists():
            with np.load(self.path, allow_pickle=False) as f:
                self._data = dict(zip(f["keys"].tolist(), f["vectors"]))
            logger.debug("vector cache %s: %d entries", self.path, len(self._data))

    def get(self, key: str) -> np.ndarray | None:
        """Return the cached vector for key, or None."""
        return self._data.get(key)

    def put_many(self, keys: list[str], vectors: np.ndarray) -> None:
        """Add vectors and write the file atomically (temp file, then replace)."""
        for k, v in zip(keys, vectors):
            self._data[k] = v
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.stem + ".tmp.npz")
        np.savez(tmp, keys=np.array(list(self._data), dtype=str), vectors=np.stack(list(self._data.values())))
        os.replace(tmp, self.path)


class TextEmbedder(BaseEstimator, TransformerMixin):
    """sklearn transformer: cleaned text column(s) -> dense, L2-normalised float32 embeddings.

    fit() learns nothing (the model is pretrained). Several text columns are joined into one string
    per row with field labels ("message: ... | body: ...") and embedded once. Input is expected to be
    the output of parse_lines(), i.e. already cleaned and secret-masked.
    `embed_fn(texts) -> array` replaces the real model (tests use a fake one to run offline).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        batch_size: int = 64,
        use_cache: bool = True,
        cache_dir: str | Path | None = None,
        embed_fn: Callable[[list[str]], np.ndarray] | None = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        self.embed_fn = embed_fn

    def fit(self, X: Any, y: Any = None) -> "TextEmbedder":
        """Nothing to learn from our data; records the input columns only."""
        self.columns_ = _column_names(X)
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Return (n_rows, dim) float32 unit vectors, reading and filling the disk cache."""
        texts = _rows_as_text(X)
        unique = list(dict.fromkeys(texts))  # embed each distinct text once
        keys = {t: _cache_key(self.model_name, t) for t in unique}
        cache = VectorCache(self.model_name, Path(self.cache_dir or VECTOR_CACHE_DIR)) if self.use_cache else None
        found: dict[str, np.ndarray] = {}
        if cache is not None:
            for t in unique:
                v = cache.get(keys[t])
                if v is not None:
                    found[t] = v
        missing = [t for t in unique if t not in found]
        if missing:
            new = self._embed(missing)
            found.update(zip(missing, new))
            if cache is not None:
                cache.put_many([keys[t] for t in missing], new)
        logger.info("embedded %d rows: %d distinct, %d from cache, %d new", len(texts), len(unique), len(unique) - len(missing), len(missing))
        if not texts:
            return np.zeros((0, getattr(self, "dim_", 0)), dtype=np.float32)
        out = l2_normalise(np.stack([found[t] for t in texts]))
        self.dim_ = out.shape[1]
        return out

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Embed in batches of batch_size with the real model or the injected embed_fn."""
        parts = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            if self.embed_fn is not None:
                parts.append(np.asarray(self.embed_fn(batch), dtype=np.float32))
            else:
                parts.append(embed_texts(batch, self.model_name, self.batch_size))
        return l2_normalise(np.vstack(parts))

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        """Names emb_0 .. emb_{dim-1} (dim is known after the first transform)."""
        dim = getattr(self, "dim_", None)
        if dim is None:
            raise AttributeError("dimension unknown until transform() has run once")
        return np.array([f"emb_{i}" for i in range(dim)], dtype=object)


def _column_names(X: Any) -> list[str]:
    """Column names of a DataFrame/Series input (empty for plain arrays)."""
    if isinstance(X, pd.DataFrame):
        return [str(c) for c in X.columns]
    if isinstance(X, pd.Series) and X.name is not None:
        return [str(X.name)]
    return []


def _rows_as_text(X: Any) -> list[str]:
    """One string per row: a single column as-is; several joined as 'col: value | col: value'."""
    if isinstance(X, pd.DataFrame):
        if X.shape[1] == 1:
            return X.iloc[:, 0].fillna("").astype(str).tolist()
        return [" | ".join(f"{c}: {v}" for c, v in zip(X.columns, row)) for row in X.fillna("").astype(str).itertuples(index=False)]
    if isinstance(X, pd.Series):
        return X.fillna("").astype(str).tolist()
    arr = np.asarray(X, dtype=object)
    if arr.ndim == 2:
        return arr[:, 0].astype(str).tolist() if arr.shape[1] == 1 else [" | ".join(map(str, r)) for r in arr]
    return arr.astype(str).tolist()


def build_embed_features(**overrides: Any) -> ColumnTransformer:
    """Return an UNFITTED dense ColumnTransformer: embeddings for text, the TF-IDF version's steps for the rest.

    Step names: text_embed, cat, num, num_log, bool (e.g. "features__text_embed__batch_size").
    The structured steps are taken from build_features("default"), so they are identical by construction.
    """
    structured = [t for t in build_features("default").transformers if t[0] not in TEXT_STEPS]
    features = ColumnTransformer(
        [("text_embed", TextEmbedder(), CONFIG["text"])] + structured,
        remainder="drop",
        sparse_threshold=0.0,  # embeddings are dense; keep the whole matrix dense
    )
    if overrides:
        features.set_params(**overrides)
    return features

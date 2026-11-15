"""Text embeddings for semantic search. Two implementations behind one interface:

- FastEmbedder: a real sentence-embedding model (fastembed, ONNX, runs on CPU, no API calls).
- HashEmbedder: deterministic bag-of-words hashing, for tests only (offline, no model download).

Both return L2-normalised float32 rows, so cosine similarity is a plain dot product.
`name` identifies the vector space: it keys the vector cache and the gate threshold in policy.yaml."""
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

from app.config import get_settings


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return one L2-normalised float32 row per text."""
        ...


def l2_normalise(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1.0, norms)  # an all-zero row stays zero instead of becoming NaN


class FastEmbedder:
    def __init__(self, model: str, cache_dir: Path) -> None:
        from fastembed import TextEmbedding  # imported here so the hash embedder never loads onnxruntime

        self.name = model
        self._model = TextEmbedding(model_name=model, cache_dir=str(cache_dir))

    def embed(self, texts: list[str]) -> np.ndarray:
        # Tickets are compared with tickets, so queries and documents are embedded the same way.
        return l2_normalise(np.array(list(self._model.embed(texts))))


class HashEmbedder:
    """Each token is hashed into one of `dim` buckets. Uses blake2b, not hash(): Python's hash()
    changes between runs, which would make test vectors (and the cache) non-deterministic."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def embed(self, texts: list[str]) -> np.ndarray:
        from app.pipeline.retrieve import tokenize  # same tokens as BM25

        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                bucket = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "little")
                out[row, bucket % self.dim] += 1.0
        return l2_normalise(out)


def embedder_name() -> str:
    """Name of the configured embedder, without loading any model (used to look up its threshold)."""
    s = get_settings()
    return HashEmbedder().name if s.embedder == "hash" else s.embed_model


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedder == "hash":
        return HashEmbedder()
    return FastEmbedder(s.embed_model, s.embed_cache_dir)

"""Tests for the UC4 embedding features (app/uc4/ml/embed_features.py). A fake embedder keeps them offline."""
import hashlib

import numpy as np
import pandas as pd
import pytest

from app.uc4.ml import embed_features as ef
from app.uc4.ml.features import build_features, get_split, parse_lines

DIM = 16
LINES = [
    "status=401 route=GET /v1/search code=ERR_AUTH_TOKEN_EXPIRED message=Bearer token expired has_www_authenticate",
    "status=429 route=POST /v1/payments code=ERR_RATE_LIMITED message=Too many requests has_retry_after ratelimit_remaining=0",
    "status=500 route=GET /v1/orders/{id} code=ERR_DB_POOL_EXHAUSTED message=Timed out acquiring DB connection: pool exhausted (max=50, waiting=88)",
    "status=403 route=GET /v1/customers/{id} code=ERR_IP_NOT_ALLOWED message=Source IP 192.0.2.45 is not allowlisted for this account",
]


class FakeEmbed:
    """Deterministic stand-in for the model: hash each text to a vector, and count calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.texts: list[str] = []

    def __call__(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        self.texts += texts
        out = []
        for t in texts:
            seed = int.from_bytes(hashlib.sha256(t.encode()).digest()[:4], "little")
            out.append(np.random.default_rng(seed).normal(size=DIM) * 3)  # not unit length on purpose
        return np.array(out)


@pytest.fixture
def fake() -> FakeEmbed:
    return FakeEmbed()


def test_text_embedder_shape_and_unit_norm(fake: FakeEmbed, tmp_path) -> None:
    X = parse_lines(LINES)
    out = ef.TextEmbedder(embed_fn=fake, cache_dir=tmp_path).fit(X["message"]).transform(X["message"])
    assert out.shape == (len(LINES), DIM) and out.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(out, axis=1), 1.0, rtol=1e-5)


def test_text_embedder_batches(fake: FakeEmbed, tmp_path) -> None:
    X = parse_lines(LINES)
    ef.TextEmbedder(embed_fn=fake, cache_dir=tmp_path, batch_size=3).transform(X["message"])
    assert fake.calls == 2  # 4 distinct texts in batches of 3


def test_cache_returns_identical_vectors_without_re_embedding(fake: FakeEmbed, tmp_path) -> None:
    X = parse_lines(LINES)
    first = ef.TextEmbedder(embed_fn=fake, cache_dir=tmp_path).transform(X["message"])
    calls = fake.calls
    second = ef.TextEmbedder(embed_fn=fake, cache_dir=tmp_path).transform(X["message"])  # new object, same disk cache
    assert fake.calls == calls
    np.testing.assert_array_equal(first, second)
    assert list(tmp_path.glob("embeddings_*.npz"))


def test_cache_key_depends_on_model(fake: FakeEmbed, tmp_path) -> None:
    X = parse_lines(LINES[:1])
    ef.TextEmbedder(model_name="model-a", embed_fn=fake, cache_dir=tmp_path).transform(X["message"])
    ef.TextEmbedder(model_name="model-b", embed_fn=fake, cache_dir=tmp_path).transform(X["message"])
    assert fake.calls == 2


def test_duplicate_rows_are_embedded_once(fake: FakeEmbed, tmp_path) -> None:
    X = parse_lines(LINES[:1] * 5)
    out = ef.TextEmbedder(embed_fn=fake, cache_dir=tmp_path).transform(X["message"])
    assert out.shape == (5, DIM) and len(fake.texts) == 1


def test_several_text_columns_are_joined_with_labels(fake: FakeEmbed, tmp_path) -> None:
    frame = pd.DataFrame({"error": ["bad token"], "body": ["{}"]})
    ef.TextEmbedder(embed_fn=fake, cache_dir=tmp_path).transform(frame)
    assert fake.texts == ["error: bad token | body: {}"]


def test_build_embed_features_fits_tiny_frame_dense(fake: FakeEmbed, tmp_path) -> None:
    X = parse_lines(LINES)
    features = ef.build_embed_features(text_embed__embed_fn=fake, text_embed__cache_dir=tmp_path).fit(X)
    out = features.transform(X)
    assert isinstance(out, np.ndarray)
    assert out.shape[0] == len(LINES) and out.shape[1] > DIM
    assert np.isfinite(out).all()


def test_structured_steps_match_tfidf_version() -> None:
    embed_steps = {name: (repr(t), cols) for name, t, cols in ef.build_embed_features().transformers if name != "text_embed"}
    tfidf_steps = {name: (repr(t), cols) for name, t, cols in build_features("default").transformers if name not in ef.TEXT_STEPS}
    assert embed_steps == tfidf_steps
    assert [n for n, *_ in ef.build_embed_features().transformers][0] == "text_embed"


def test_uses_same_test_rows_as_tfidf_split() -> None:
    assert ef.get_split is get_split  # imported, not copied
    a = ef.get_split()
    b = get_split()
    pd.testing.assert_frame_equal(a[1], b[1])
    pd.testing.assert_series_equal(a[3], b[3])

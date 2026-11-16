"""Tests for the shared UC4 feature module (app/uc4/ml/features.py)."""
import numpy as np
import pandas as pd

from app.uc4.ml.features import CONFIG, build_features, clean_text, get_groups, get_split, parse_lines

LINES = [
    "status=401 route=GET /v1/search code=ERR_AUTH_TOKEN_EXPIRED message=Bearer token expired has_www_authenticate",
    "status=401 route=POST /v1/payments code=ERR_AUTH_TOKEN_EXPIRED message=Bearer token expired has_www_authenticate",
    "status=429 route=POST /v1/payments code=ERR_RATE_LIMITED message=Too many requests has_retry_after ratelimit_remaining=0",
    "status=429 route=POST /v1/orders code=ERR_RATE_LIMITED message=Too many requests ratelimit_remaining=3",
    "status=500 route=GET /v1/orders/{id} code=ERR_DB_POOL_EXHAUSTED message=Timed out acquiring DB connection: pool exhausted (max=50, waiting=88)",
    "status=500 route=GET /v1/orders/{id} code=ERR_DB_POOL_EXHAUSTED message=Timed out acquiring DB connection: pool exhausted (max=50, waiting=307)",
    "status=403 route=GET /v1/customers/{id} code=ERR_IP_NOT_ALLOWED message=Source IP 192.0.2.45 is not allowlisted for this account",
    "status=403 route=GET /v1/customers/{id} code=ERR_IP_NOT_ALLOWED message=Source IP 192.0.2.118 is not allowlisted for this account",
]


def test_clean_text_keeps_error_codes_and_status() -> None:
    out = clean_text("ERR_QUOTA_429 invalid_token status 401 ERR_AUTH_TOKEN_EXPIRED")
    assert out == "err_quota_429 invalid_token status 401 err_auth_token_expired"


def test_clean_text_keeps_plain_bearer_words() -> None:
    assert clean_text("Bearer token expired") == "bearer token expired"


def test_clean_text_masks_secrets_and_ids() -> None:
    raw = (
        "Authorization: Bearer abc.DEF-ghi_123 key=nvp_live_9f8e7d6c5b4a "
        "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig_part-1 api_key=s3cr3tvalue "
        "from 203.0.113.24 user jane.doe@example.com id 123e4567-e89b-12d3-a456-426614174000 "
        "corr c-68e38afa09 req req_a6ef78b4819136 at 2026-10-05T00:19:43.439Z hash deadbeef12345678 n=1234567"
    )
    out = clean_text(raw)
    for leaked in ("abc.DEF", "nvp_live_", "eyJ", "s3cr3tvalue", "203.0.113.24", "jane.doe", "123e4567",
                   "c-68e38afa09", "req_a6ef", "2026-10-05", "deadbeef12345678", "1234567"):
        assert leaked.lower() not in out, f"{leaked} leaked: {out}"
    for placeholder in ("<TOKEN>", "<API_KEY>", "<JWT>", "<SECRET>", "<IP>", "<EMAIL>", "<UUID>",
                        "<CORR_ID>", "<REQ_ID>", "<TS>", "<HEX>", "<NUM>"):
        assert placeholder in out, f"{placeholder} missing: {out}"


def test_parse_lines_extracts_columns() -> None:
    X = parse_lines(LINES)
    assert list(X.columns)[0] == CONFIG["text"]
    assert X.loc[2, "status"] == "429"
    assert X.loc[2, "has_retry_after"] == 1 and X.loc[2, "ratelimit_remaining"] == 0
    assert X.loc[0, "has_www_authenticate"] == 1 and "has_www_authenticate" not in X.loc[0, "message"]
    assert X.loc[5, "db_pool_waiting"] == 307 and X.loc[5, "has_db_pool_waiting"] == 1
    assert np.isnan(X.loc[0, "db_pool_waiting"])
    assert "<IP>" in X.loc[6, "message"]


def test_build_features_fits_tiny_frame() -> None:
    X = parse_lines(LINES)
    features = build_features().fit(X)
    out = features.transform(X)
    assert out.shape[0] == len(LINES)
    dense = out.toarray() if hasattr(out, "toarray") else out
    assert np.isfinite(dense).all()
    # Unknown category and unseen route at predict time must not crash.
    new = parse_lines(["status=418 route=GET /v1/teapot code=ERR_TEAPOT message=I am a teapot"])
    assert features.transform(new).shape[1] == out.shape[1]


def test_build_features_overrides_use_stable_names() -> None:
    features = build_features(text_word__ngram_range=(1, 1), text_char__min_df=1)
    params = features.get_params()
    assert params["text_word__ngram_range"] == (1, 1)
    assert params["text_char__min_df"] == 1
    assert {"text_word", "text_char", "cat", "num", "num_log", "bool"} <= {n for n, *_ in features.transformers}


def test_nb_mode_is_non_negative_even_outside_train_range() -> None:
    X = parse_lines(LINES)
    features = build_features("nb").fit(X)
    wild = parse_lines([
        "status=429 route=POST /v1/payments code=ERR_RATE_LIMITED message=Too many requests ratelimit_remaining=999",
        "status=500 route=GET /v1/orders/{id} code=ERR_DB_POOL_EXHAUSTED message=pool exhausted (max=50, waiting=0)",
    ])
    for frame in (X, wild):
        out = features.transform(frame)
        assert out.min() >= 0


def test_get_split_is_fixed_and_case_grouped() -> None:
    a = get_split()
    b = get_split()
    for left, right in zip(a, b):
        pd.testing.assert_index_equal(left.index, right.index)
    pd.testing.assert_frame_equal(a[1], b[1])
    pd.testing.assert_series_equal(a[3], b[3])
    assert not set(get_groups("train")) & set(get_groups("test"))
    assert len(a[0]) == len(get_groups("train")) and len(a[1]) == len(get_groups("test"))


def test_dataset_has_no_excluded_columns() -> None:
    X_train, X_test, _, _ = get_split()
    for X in (X_train, X_test):
        assert not set(CONFIG["exclude"]) & set(X.columns)

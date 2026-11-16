"""Tests for the UC4 TF-IDF features and dataset."""
import numpy as np

from app.uc4.features import tfidf_features
from app.uc4.tfidf_data import CSV_NAME, build_tfidf, load_split

TRAIN_TEXT = [
    "status=401 code=ERR_AUTH_TOKEN_EXPIRED message=Bearer token expired",
    "status=401 code=ERR_AUTH_TOKEN_EXPIRED message=Bearer token expired",
    "status=429 code=ERR_RATE_LIMITED message=Rate limit exceeded",
    "status=429 code=ERR_RATE_LIMITED message=Rate limit exceeded",
    "status=504 code=ERR_UPSTREAM_TIMEOUT message=Upstream timeout",
    "status=504 code=ERR_UPSTREAM_TIMEOUT message=Upstream timeout",
]
TEST_TEXT = ["status=401 zqxjtoken message=Bearer token expired zqxjtoken"]


def _fitted():
    """A union fitted on the small train sample."""
    union = tfidf_features()
    union.fit(TRAIN_TEXT)
    return union


def _vocabs(union) -> dict[str, dict]:
    """Copy of each sub-vectorizer's vocabulary."""
    return {name: dict(vec.vocabulary_) for name, vec in union.transformer_list}


def test_tfidf_features_returns_a_new_unfitted_union_each_call():
    a, b = tfidf_features(), tfidf_features()
    assert a is not b
    for _, vec in a.transformer_list:
        assert not hasattr(vec, "vocabulary_")


def test_token_seen_only_in_test_is_not_in_word_vocabulary():
    union = _fitted()
    union.transform(TEST_TEXT)
    words = dict(union.transformer_list)["words"]
    assert "zqxjtoken" not in words.vocabulary_
    assert "token" in words.vocabulary_


def test_transforming_test_text_does_not_change_the_vocabulary():
    union = _fitted()
    before = _vocabs(union)
    union.transform(TEST_TEXT)
    assert _vocabs(union) == before


def test_validation_split_reads_the_calibration_file():
    assert CSV_NAME["validation"] == "classifier_calibration.csv"
    rows, _ = load_split("validation")
    assert len(rows) == 133


def test_train_excludes_insufficient_cases_and_returns_them_separately():
    rows, insufficient = load_split("train")
    assert len(rows) == 422
    assert all(r["expected_cause"] is not None for r in rows)
    assert {r["case_id"] for r in insufficient} == {"UC4-0085"}
    assert len(insufficient) == 5


def test_test_split_keeps_insufficient_cases_flagged():
    rows, insufficient = load_split("test")
    assert len(rows) == 303
    flagged = {r["case_id"] for r in rows if r["insufficient"]}
    assert flagged == {"UC4-0087", "UC4-0088", "UC4-0089", "UC4-0090"}
    assert all(r["expected_cause"] is None for r in rows if r["insufficient"])
    assert len(insufficient) == 9


def test_matrix_shapes_match_row_counts():
    result = build_tfidf()
    width = result["matrices"]["train"].shape[1]
    for split, matrix in result["matrices"].items():
        assert matrix.shape == (len(result["rows"][split]), width)


def test_same_input_gives_the_same_matrices():
    a, b = build_tfidf(), build_tfidf()
    assert _vocabs(a["union"]) == _vocabs(b["union"])
    for split in a["matrices"]:
        ma, mb = a["matrices"][split], b["matrices"][split]
        assert ma.shape == mb.shape
        assert (ma != mb).nnz == 0
        assert np.array_equal(ma.indices, mb.indices)

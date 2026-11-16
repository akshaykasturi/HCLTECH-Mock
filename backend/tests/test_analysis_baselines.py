"""Evaluation baselines (app/analysis/baselines.py). Moved from Akhilesh's test_uc4_tfidf.py, plus the majority baseline."""
import numpy as np
import pytest

from app.analysis.baselines import baseline_rows, majority_baseline, text_only_baseline, text_tfidf
from app.uc4.ml.features import CONFIG

TRAIN_TEXT = [
    "bearer token expired", "bearer token expired",
    "rate limit exceeded", "rate limit exceeded",
    "upstream timeout", "upstream timeout",
]
TEST_TEXT = ["zqxjtoken bearer token expired zqxjtoken"]


def _vocabs(union) -> dict[str, dict]:
    return {name: dict(vec.vocabulary_) for name, vec in union.transformer_list}


@pytest.fixture(scope="module")
def class_result():
    return text_only_baseline("class")


def test_majority_baseline_returns_the_most_common_label() -> None:
    assert majority_baseline(["a", "b", "b", "c", "b"], 3) == ["b", "b", "b"]
    assert majority_baseline(["y", "x"], 1) == ["x"]  # tie: alphabetically first
    with pytest.raises(ValueError):
        majority_baseline([], 2)


def test_word_seen_only_in_test_is_not_in_the_vocabulary() -> None:
    union = text_tfidf().fit(TRAIN_TEXT)
    before = _vocabs(union)
    union.transform(TEST_TEXT)
    words = dict(union.transformer_list)["words"]
    assert "zqxjtoken" not in words.vocabulary_
    assert "token" in words.vocabulary_
    assert _vocabs(union) == before  # transforming test text does not change the vocabulary


def test_baseline_vocabulary_is_fitted_on_train_only(class_result) -> None:
    train = baseline_rows("train")
    train = train[~train["insufficient"]]
    expected = text_tfidf().fit(train["text"].tolist())
    assert _vocabs(class_result.model.named_steps["tfidf"]) == _vocabs(expected)


def test_validation_split_reads_the_calibration_file() -> None:
    assert CONFIG["files"]["validation"] == "classifier_calibration.csv"
    assert len(baseline_rows("validation")) == 133


def test_insufficient_cases_excluded_from_train_and_flagged_in_test(class_result) -> None:
    train = baseline_rows("train")
    assert set(train[train["insufficient"]]["case_id"]) == {"UC4-0085"}
    assert int((~train["insufficient"]).sum()) == 422  # rows the baseline trains on

    flagged = {cid for cid, ins in zip(class_result.case_ids, class_result.insufficient) if ins}
    assert flagged == {"UC4-0087", "UC4-0088", "UC4-0089", "UC4-0090"}
    assert len(class_result.case_ids) == 303 and int(class_result.insufficient.sum()) == 9

    cause = text_only_baseline("cause")
    assert all(y is None for y, ins in zip(cause.y_true, cause.insufficient) if ins)
    assert None not in cause.classes


def test_same_input_gives_the_same_output(class_result) -> None:
    again = text_only_baseline("class")
    assert np.array_equal(class_result.predictions, again.predictions)
    assert np.allclose(class_result.probabilities, again.probabilities)


def test_probabilities_match_predictions(class_result) -> None:
    assert class_result.probabilities.shape == (303, len(class_result.classes))
    assert np.allclose(class_result.probabilities.sum(axis=1), 1.0)
    best = np.array(class_result.classes)[class_result.probabilities.argmax(axis=1)]
    assert np.array_equal(best, class_result.predictions)


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(ValueError):
        text_only_baseline("route")

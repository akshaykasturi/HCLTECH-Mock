"""UC4 ComplementNB and RandomForest cause classifiers: probabilities, repeatability, no leakage."""
import numpy as np
import pytest

import scripts.train_nb_rf_uc4 as train_script
from app.uc4.classifier import CauseClassifier, grouped_folds
from app.uc4.evaluate_classifier import confused_pairs, score_cases
from app.uc4.ml import cause_data
from app.uc4.ml.cause_data import load_cause_split
from app.uc4.ml.features import build_features
from app.uc4.nb_rf import complement_nb, random_forest, tune

SMALL = {"complement_nb": lambda: complement_nb(alpha=1.0),
         "random_forest": lambda: random_forest(n_estimators=10, max_depth=10)}


@pytest.fixture(scope="module")
def train():
    return load_cause_split("train")


@pytest.fixture(scope="module")
def validation():
    return load_cause_split("validation")


@pytest.fixture(scope="module")
def fitted(train):
    return {name: make().fit(train.X, train.y, groups=train.case_id) for name, make in SMALL.items()}


def _words(pipeline) -> set[str]:
    return set(pipeline.named_steps["features"].named_transformers_["text_word"].vocabulary_)


# ---------- rows ----------

def test_train_has_no_insufficient_cases_and_validation_keeps_them_flagged(train, validation):
    assert not train.insufficient.any() and all(y is not None for y in train.y)
    assert validation.insufficient.any()
    assert all(y is None for y in validation.y[validation.insufficient])


def test_each_case_has_exactly_one_focal_row(validation):
    focal = validation.focal()
    assert len(focal) == len(set(validation.case_id)) == len(set(focal.case_id))


def test_no_case_is_in_two_splits(train, validation):
    test = load_cause_split("test")
    assert not set(train.case_id) & set(validation.case_id)
    assert not set(train.case_id) & set(test.case_id)
    assert not set(validation.case_id) & set(test.case_id)


# ---------- interface and probabilities ----------

@pytest.mark.parametrize("name", list(SMALL))
def test_follows_the_shared_interface(fitted, name):
    model = fitted[name]
    assert isinstance(model, CauseClassifier)
    assert model.model_name == name and model.feature_set == "tfidf"
    assert len(model.classes_) == 14


@pytest.mark.parametrize("name", list(SMALL))
def test_probabilities_sum_to_one_and_top_matches(fitted, validation, name):
    labels, top, probs = fitted[name].predict(validation.X)
    assert probs.shape == (len(validation), len(fitted[name].classes_))
    assert np.allclose(probs.sum(axis=1), 1.0)
    assert np.array_equal(top, probs.max(axis=1))
    assert np.array_equal(labels, fitted[name].classes_[probs.argmax(axis=1)])


def test_fit_requires_case_groups(train):
    with pytest.raises(ValueError):
        complement_nb().fit(train.X, train.y)


# ---------- repeatability ----------

@pytest.mark.parametrize("name", list(SMALL))
def test_same_seed_gives_the_same_predictions(fitted, train, validation, name):
    again = SMALL[name]().fit(train.X, train.y, groups=train.case_id)
    first, second = fitted[name].predict(validation.X), again.predict(validation.X)
    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[2], second[2])


# ---------- nothing fitted on validation or test ----------

def test_calibration_folds_never_split_a_case(train):
    for fit_rows, cal_rows in grouped_folds(train.y, train.case_id):
        assert not set(train.case_id[fit_rows]) & set(train.case_id[cal_rows])
        assert set(train.y[fit_rows]) == set(train.y)  # every cause can still be learned


@pytest.mark.parametrize("name", list(SMALL))
def test_features_are_fitted_on_train_fold_rows_only(fitted, train, validation, name):
    model = fitted[name]
    test = load_cause_split("test")
    unseen = (_words_of(validation) | _words_of(test)) - _words_of(train)
    assert unseen, "need words that appear only outside train for this test to mean something"
    for calibrated, (fit_rows, _) in zip(model.model_.calibrated_classifiers_, model.folds_):
        vocab = _words(calibrated.estimator)
        assert vocab == _vocab_fitted_on(train.X.iloc[fit_rows])
        assert not vocab & unseen


def _words_of(split) -> set[str]:
    return _vocab_fitted_on(split.X)


def _vocab_fitted_on(X) -> set[str]:
    return set(build_features().fit(X).named_transformers_["text_word"].vocabulary_)


def test_training_script_never_loads_test(monkeypatch, tmp_path, capsys):
    real = cause_data.load_cause_split
    loaded = []

    def guarded(split):
        loaded.append(split)
        if split == "test":
            raise AssertionError("the training script loaded the test split")
        return real(split)

    monkeypatch.setattr(train_script, "load_cause_split", guarded)
    monkeypatch.setattr(train_script, "MODEL_DIR", tmp_path / "models" / "uc4")
    monkeypatch.setattr(train_script, "MODELS", {"complement_nb": (complement_nb, [{"alpha": 1.0}])})
    train_script.main()
    assert sorted(set(loaded)) == ["train", "validation"]
    assert (tmp_path / "models" / "uc4" / "complement_nb_tfidf.joblib").exists()


def test_tune_picks_the_best_setting_by_f1_then_brier(train, validation):
    model, rows = tune(complement_nb, [{"alpha": 1.0}, {"alpha": 0.01}], train, validation)
    assert len(rows) == 2
    best = min(range(2), key=lambda i: (-rows[i]["macro_f1"], rows[i]["brier"], i))
    assert model.params == rows[best]["params"]


# ---------- evaluation helpers ----------

def test_confused_pairs_counts_mistakes_most_frequent_first():
    y = ["a", "a", "a", "b", "b", "c"]
    p = ["b", "b", "a", "a", "b", "a"]
    assert confused_pairs(y, p) == [("a", "b", 2), ("b", "a", 1), ("c", "a", 1)]


def test_score_cases_on_a_perfect_model():
    s = score_cases(["a", "b"], ["a", "b"], [1.0, 1.0])
    assert s["n"] == 2
    for metric, value in (("accuracy", 1.0), ("macro_f1", 1.0), ("ece", 0.0), ("brier", 0.0)):
        assert s[metric] == pytest.approx((value, value, value))

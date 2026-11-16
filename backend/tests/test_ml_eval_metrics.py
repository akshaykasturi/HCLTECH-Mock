"""Tests for the UC4 evaluation metrics, model comparison and rules baseline, on tiny hand-made examples."""
import json
import math

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    log_loss,
    matthews_corrcoef,
    precision_recall_fscore_support,
    roc_auc_score,
)

from app.uc4.ml.compare_models import compare, to_markdown
from app.uc4.ml.eval_metrics import brier_multiclass, ece, evaluate
from app.uc4.ml.train_models import RulesBaseline

CLASSES = ["a", "b", "c"]
Y_TRUE = np.array(["a", "a", "a", "b", "b", "c"])
Y_PRED = np.array(["a", "a", "b", "b", "c", "c"])
PROBA = np.array([
    [0.8, 0.1, 0.1],
    [0.6, 0.3, 0.1],
    [0.3, 0.6, 0.1],
    [0.2, 0.7, 0.1],
    [0.1, 0.3, 0.6],
    [0.1, 0.2, 0.7],
])


def _no_nan(obj) -> bool:
    """True if no float NaN/inf appears anywhere in a nested dict/list."""
    if isinstance(obj, float):
        return math.isfinite(obj)
    if isinstance(obj, dict):
        return all(_no_nan(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nan(v) for v in obj)
    return True


def test_one_vs_rest_counts_match_hand_computed() -> None:
    # Confusion (rows true, cols predicted): a=[2,1,0], b=[0,1,1], c=[0,0,1]
    pc = evaluate(Y_TRUE, Y_PRED, PROBA, CLASSES, n_boot=10)["per_class"]
    assert (pc["a"]["TP"], pc["a"]["FP"], pc["a"]["FN"], pc["a"]["TN"]) == (2, 0, 1, 3)
    assert (pc["b"]["TP"], pc["b"]["FP"], pc["b"]["FN"], pc["b"]["TN"]) == (1, 1, 1, 3)
    assert (pc["c"]["TP"], pc["c"]["FP"], pc["c"]["FN"], pc["c"]["TN"]) == (1, 1, 0, 4)
    assert pc["a"]["specificity"] == 1.0 and pc["c"]["specificity"] == 0.8
    assert pc["b"]["fpr"] == 0.25 and pc["a"]["fnr"] == pytest.approx(1 / 3)


def test_metrics_agree_with_sklearn() -> None:
    r = evaluate(Y_TRUE, Y_PRED, PROBA, CLASSES, n_boot=10)
    o, pc = r["overall"], r["per_class"]
    p, rec, f1, _ = precision_recall_fscore_support(Y_TRUE, Y_PRED, labels=CLASSES, zero_division=0)
    for i, c in enumerate(CLASSES):
        assert pc[c]["precision"] == pytest.approx(p[i])
        assert pc[c]["recall"] == pytest.approx(rec[i])
        assert pc[c]["f1"] == pytest.approx(f1[i])
        assert pc[c]["roc_auc"] == pytest.approx(roc_auc_score(Y_TRUE == c, PROBA[:, i]))
    for avg in ("macro", "weighted", "micro"):
        sk = precision_recall_fscore_support(Y_TRUE, Y_PRED, labels=CLASSES, average=avg, zero_division=0)
        assert (o[f"{avg}_precision"], o[f"{avg}_recall"], o[f"{avg}_f1"]) == pytest.approx(sk[:3])
    assert o["accuracy"] == pytest.approx(accuracy_score(Y_TRUE, Y_PRED))
    assert o["balanced_accuracy"] == pytest.approx(balanced_accuracy_score(Y_TRUE, Y_PRED))
    assert o["mcc"] == pytest.approx(matthews_corrcoef(Y_TRUE, Y_PRED))
    assert o["cohen_kappa"] == pytest.approx(cohen_kappa_score(Y_TRUE, Y_PRED))
    assert o["log_loss"] == pytest.approx(log_loss(Y_TRUE, PROBA, labels=CLASSES))
    assert o["top2_accuracy"] == 1.0  # every true class is in the top 2
    assert r["confusion"]["counts"] == [[2, 1, 0], [0, 1, 1], [0, 0, 1]]
    assert r["most_confused"][0]["count"] == 1


def test_brier_and_ece_hand_values() -> None:
    assert brier_multiclass(np.array(["a", "a"]), np.array([[1.0, 0, 0], [0, 1.0, 0]]), CLASSES) == pytest.approx(1.0)  # (0 + 2) / 2
    value, _ = ece(np.array(["a", "b"]), np.array([[1.0, 0, 0], [0, 1.0, 0]]), CLASSES)
    assert value == 0.0
    value, _ = ece(np.array(["a", "a"]), np.array([[0.9, 0.1, 0], [0.1, 0.9, 0]]), CLASSES)
    assert value == pytest.approx(0.4)  # one bin: confidence 0.9, accuracy 0.5 -> |0.5 - 0.9| = 0.4


def test_zero_support_and_never_predicted_classes_are_na_not_nan() -> None:
    classes = ["a", "b", "c", "d"]  # d: no rows and never predicted
    y_true = np.array(["a", "a", "b", "c"])
    y_pred = np.array(["a", "a", "b", "b"])  # c is never predicted
    proba = np.array([[0.7, 0.1, 0.1, 0.1]] * 4)
    r = evaluate(y_true, y_pred, proba, classes, n_boot=20)
    d, c = r["per_class"]["d"], r["per_class"]["c"]
    assert d["support"] == 0 and d["precision"] is None and d["recall"] is None and d["f1"] is None and d["roc_auc"] is None
    assert c["precision"] is None and c["recall"] == 0.0
    assert r["confusion"]["row_normalised"][3] == [None, None, None, None]
    assert _no_nan(r)
    json.dumps(r)  # JSON-ready


def test_baseline_without_probabilities_gets_na() -> None:
    r = evaluate(Y_TRUE, Y_PRED, None, CLASSES, n_boot=10)
    for key in ("top2_accuracy", "log_loss", "brier", "ece"):
        assert r["overall"][key] is None
    assert r["per_class"]["a"]["roc_auc"] is None and r["per_class"]["a"]["pr_auc"] is None
    assert r["has_probabilities"] is False and r["overall"]["macro_f1"] is not None


def test_bootstrap_resamples_cases_when_groups_given() -> None:
    groups = ["g1", "g1", "g2", "g3", "g3", "g4"]
    b = evaluate(Y_TRUE, Y_PRED, None, CLASSES, groups=groups, n_boot=200)["bootstrap_95ci"]
    assert b["unit"] == {"resampled": "cases", "n_units": 4, "n_resamples": 200, "seed": 42}
    for key in ("accuracy", "balanced_accuracy", "macro_f1"):
        assert b[key]["low"] <= b[key]["point"] <= b[key]["high"]
    again = evaluate(Y_TRUE, Y_PRED, None, CLASSES, groups=groups, n_boot=200)["bootstrap_95ci"]
    assert again == b  # seeded


def test_mcnemar_identical_predictions_gives_p_1_and_tie_prefers_simpler_model() -> None:
    results = {
        name: evaluate(Y_TRUE, Y_PRED, None if name == "rules" else PROBA, CLASSES, n_boot=50)
        for name in ("rules", "tfidf/rf", "tfidf/lr")
    }
    preds = {name: Y_PRED for name in results}
    report = compare(results, preds, Y_TRUE)
    assert all(p["p_value"] == 1.0 and not p["significant"] for p in report["mcnemar"])
    assert report["recommendation"]["model"] == "tfidf/lr"  # tied -> LR before RF
    assert any("does not beat the rules baseline" in w for w in report["warnings"])
    assert "N/A" in to_markdown(report, results)  # rules has no ECE


def test_compare_rejects_different_test_rows() -> None:
    results = {"a": evaluate(Y_TRUE, Y_PRED, None, CLASSES, n_boot=5)}
    with pytest.raises(ValueError):
        compare(results, {"a": Y_PRED[:-1]}, Y_TRUE)


def test_rules_baseline_learns_status_majority() -> None:
    X = pd.DataFrame({"status": ["401", "401", "429", "504", "504", "504"]})
    y = pd.Series(["authentication", "authentication", "rate_limit", "timeout", "timeout", "rate_limit"])
    rules = RulesBaseline().fit(X, y)
    pred = rules.predict(pd.DataFrame({"status": ["401", "504", "418"]}))
    assert list(pred) == ["authentication", "timeout", "authentication"]  # 418 unseen -> most common class
    assert not hasattr(rules, "predict_proba")

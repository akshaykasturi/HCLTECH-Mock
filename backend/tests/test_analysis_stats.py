"""Hand-worked examples for app.analysis.stats."""
import math

import numpy as np
import pytest

from app.analysis.stats import bootstrap_ci, bootstrap_stat, brier, ece, mcnemar, risk_coverage


def test_brier_matches_hand_worked_example():
    # (0.9-1)^2 + (0.6-0)^2 + (0.8-1)^2 = 0.01 + 0.36 + 0.04 = 0.41, over 3 items
    assert brier([0.9, 0.6, 0.8], [1, 0, 1]) == pytest.approx(0.41 / 3)


def test_brier_is_zero_for_a_perfect_model():
    assert brier([1.0, 0.0, 1.0], [True, False, True]) == 0.0


def test_brier_rejects_different_lengths():
    with pytest.raises(ValueError):
        brier([0.5, 0.5], [1])


def test_bootstrap_constant_values_give_a_zero_width_interval():
    assert bootstrap_ci([0.7] * 20) == pytest.approx((0.7, 0.7, 0.7))


def test_bootstrap_is_repeatable_with_the_same_seed():
    values = [0, 1, 1, 0, 1, 1, 1, 0, 1, 1]
    assert bootstrap_ci(values) == bootstrap_ci(values)


def test_bootstrap_point_is_the_mean_and_inside_the_interval():
    point, low, high = bootstrap_ci([0, 1, 1, 0, 1, 1, 1, 0, 1, 1])
    assert point == pytest.approx(0.7)
    assert low <= point <= high


def test_bootstrap_interval_for_half_right_out_of_100_is_about_40_to_60():
    # Standard error = sqrt(0.5 * 0.5 / 100) = 0.05, so 95% is about 0.5 +/- 0.098
    _, low, high = bootstrap_ci([0] * 50 + [1] * 50)
    assert 0.38 <= low <= 0.42
    assert 0.58 <= high <= 0.62


def test_bootstrap_rejects_empty_input():
    with pytest.raises(ValueError):
        bootstrap_ci([])


def _pairs(b: int, c: int, both_right: int = 3, both_wrong: int = 2) -> tuple[list[int], list[int]]:
    """Paired results with b items only A got right and c items only B got right."""
    a = [1] * b + [0] * c + [1] * both_right + [0] * both_wrong
    m = [0] * b + [1] * c + [1] * both_right + [0] * both_wrong
    return a, m


def test_mcnemar_uses_exact_test_for_few_disagreements():
    # n = 7 disagreements: p = 2 * (C(7,0) + C(7,1)) / 2^7 = 2 * 8 / 128 = 0.125
    result = mcnemar(*_pairs(b=1, c=6))
    assert (result["b"], result["c"], result["n"]) == (1, 6, 7)
    assert result["method"] == "exact_binomial"
    assert result["p_value"] == pytest.approx(0.125)


def test_mcnemar_uses_chi_square_with_continuity_for_many_disagreements():
    # (|30 - 10| - 1)^2 / 40 = 361 / 40 = 9.025; p = erfc(sqrt(9.025 / 2)) ~ 0.00266
    result = mcnemar(*_pairs(b=30, c=10))
    assert result["method"] == "chi2_continuity"
    assert result["statistic"] == pytest.approx(9.025)
    assert result["p_value"] == pytest.approx(math.erfc(math.sqrt(9.025 / 2)))
    assert result["p_value"] == pytest.approx(0.00266, abs=1e-5)


def test_mcnemar_gives_p_of_one_when_models_never_disagree():
    result = mcnemar([1, 0, 1], [1, 0, 1])
    assert result["n"] == 0
    assert result["p_value"] == 1.0


def test_mcnemar_rejects_different_lengths():
    with pytest.raises(ValueError):
        mcnemar([1, 0], [1])


def test_risk_coverage_matches_hand_worked_example():
    rows = risk_coverage([0.9, 0.8, 0.8, 0.3], [1, 1, 0, 0])
    assert [r["threshold"] for r in rows] == [0.9, 0.8, 0.3]
    assert [r["answered"] for r in rows] == [1, 3, 4]
    assert [r["coverage"] for r in rows] == pytest.approx([0.25, 0.75, 1.0])
    assert [r["accuracy"] for r in rows] == pytest.approx([1.0, 2 / 3, 0.5])
    assert [r["risk"] for r in rows] == pytest.approx([0.0, 1 / 3, 0.5])


def test_ece_matches_hand_worked_example():
    # Bin (0.8, 0.9]: 2 items, confidence 0.9, accuracy 1/2 -> gap 0.4, weight 2/4 -> 0.2
    # Bin (0.5, 0.6]: 2 items, confidence 0.6, accuracy 2/2 -> gap 0.4, weight 2/4 -> 0.2
    assert ece([0.9, 0.9, 0.6, 0.6], [1, 0, 1, 1]) == pytest.approx(0.4)


def test_ece_is_zero_when_confidence_equals_accuracy():
    # Both items sit in bin (0.4, 0.5]: confidence 0.5, accuracy 1/2
    assert ece([0.5, 0.5], [1, 0]) == pytest.approx(0.0)


def test_ece_puts_an_edge_value_in_the_lower_bin():
    # 0.3 goes in (0.2, 0.3], 0.35 in (0.3, 0.4]: two bins, so 0.5*|0-0.3| + 0.5*|1-0.35| = 0.475.
    # (One shared bin would give |0.5-0.325| = 0.175.)
    assert ece([0.3, 0.35], [0, 1]) == pytest.approx(0.475)


def test_ece_handles_confidence_zero_and_one():
    # 1.0 right -> gap 0; 0.0 wrong -> gap 0
    assert ece([1.0, 0.0], [1, 0]) == pytest.approx(0.0)


def test_bootstrap_stat_with_mean_matches_bootstrap_ci():
    values = [0, 1, 1, 0, 1, 1, 1, 0, 1, 1]
    assert bootstrap_stat(np.mean, values) == pytest.approx(bootstrap_ci(values))


def test_bootstrap_stat_keeps_pairs_together():
    # a always equals b, so every resample agrees fully: zero-width interval at 1.0
    a = ["x", "y", "z", "x", "y"]
    assert bootstrap_stat(lambda p, q: float(np.mean(p == q)), a, list(a)) == (1.0, 1.0, 1.0)


def test_bootstrap_stat_rejects_different_lengths():
    with pytest.raises(ValueError):
        bootstrap_stat(np.mean, [1, 2], [1])

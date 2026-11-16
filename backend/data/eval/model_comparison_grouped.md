# UC4 failure-class models: test-set comparison

Test split: 261 rows. Classes: authentication, authorization, dependency, rate_limit, server_error, timeout, validation. Intervals: 95% bootstrap over 31 test cases (1000 resamples, seed 42). Significance: alpha = 0.05.

- Same rows for every model: the template-grouped test split (test_idx_grouped.json): one message template per class never seen in training; identical class order checked.
- LinearSVC: predictions from the model itself, probabilities from its sigmoid calibration by grouped cross-validation on train.
- rules = most common class per HTTP status in train; it has no probabilities (probability metrics N/A).
- Embedding prediction times use the on-disk vector cache; a cold first call is slower.

## Recommendation

**embeddings/lr**. 4 models are statistically tied with the best (tfidf/linear_svc, embeddings/linear_svc, embeddings/lr, tfidf/lr): their macro-F1 intervals overlap and McNemar p >= 0.05. Picked embeddings/lr: Logistic Regression is the simplest model (one weight per feature and class), cheap to predict and easy to explain; among equally simple ones it has the lowest ECE.

It is NOT significantly better than the rules baseline (McNemar p = 1).

## Leaderboard (sorted by macro-F1)

| Model | Macro-F1 [95% CI] | Train acc | Test acc | Gap | Balanced acc | MCC | Top-2 acc | Log loss | ECE | Fit s | Predict ms / 100 rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rules | 0.778 [0.704, 0.828] | 0.990 | 0.801 | +0.189 | 0.836 | 0.802 | N/A | N/A | N/A | 0.0 | 0.1 |
| tfidf/linear_svc | 0.778 [0.704, 0.828] | 1.000 | 0.801 | +0.199 | 0.836 | 0.802 | 0.697 | 1.013 | 0.199 | 1.6 | 27.7 |
| embeddings/linear_svc | 0.778 [0.704, 0.828] | 1.000 | 0.801 | +0.199 | 0.836 | 0.802 | 0.824 | 1.308 | 0.226 | 2.7 | 13.3 |
| embeddings/lr | 0.768 [0.684, 0.820] | 1.000 | 0.801 | +0.199 | 0.836 | 0.796 | 0.816 | 0.789 | 0.117 | 0.5 | 8.8 |
| tfidf/lr | 0.767 [0.678, 0.827] | 1.000 | 0.808 | +0.192 | 0.843 | 0.798 | 0.816 | 0.868 | 0.169 | 0.6 | 19.7 |
| embeddings/rf | 0.406 [0.308, 0.495] | 1.000 | 0.487 | +0.513 | 0.571 | 0.456 | 0.801 | 1.707 | 0.176 | 8.6 | 19.2 |
| tfidf/rf | 0.191 [0.149, 0.242] | 1.000 | 0.314 | +0.686 | 0.286 | 0.255 | 0.755 | 1.476 | 0.371 | 8.5 | 33.7 |

Macro-F1 without the insufficient-evidence test cases (254 rows): rules 0.777, tfidf/lr 0.763, tfidf/linear_svc 0.777, tfidf/rf 0.188, embeddings/lr 0.765, embeddings/linear_svc 0.777, embeddings/rf 0.404

## Per-class F1 (best per row in bold)

| Class | rules | tfidf/linear_svc | embeddings/linear_svc | embeddings/lr | tfidf/lr | embeddings/rf | tfidf/rf |
|---|---|---|---|---|---|---|---|
| authentication | **1.000** | **1.000** | **1.000** | 0.883 | 0.883 | 0.567 | 0.338 |
| authorization | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | N/A |
| dependency | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | 0.730 | N/A |
| rate_limit | **0.919** | **0.919** | **0.919** | **0.919** | 0.818 | N/A | 0.000 |
| server_error | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | N/A | **1.000** |
| timeout | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| validation | 0.527 | 0.527 | 0.527 | 0.574 | **0.667** | 0.547 | N/A |

## One-vs-rest counts for embeddings/lr

| Class | Support | TP | FP | FN | TN | Precision | Recall | Specificity | F1 | FPR | FNR | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| authentication | 34 | 34 | 9 | 0 | 218 | 0.791 | 1.000 | 0.960 | 0.883 | 0.040 | 0.000 | 1.000 | 1.000 |
| authorization | 18 | 18 | 0 | 0 | 243 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| dependency | 46 | 46 | 0 | 0 | 215 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| rate_limit | 40 | 34 | 0 | 6 | 221 | 1.000 | 0.850 | 1.000 | 0.919 | 0.000 | 0.150 | 0.979 | 0.927 |
| server_error | 48 | 48 | 0 | 0 | 213 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| timeout | 46 | 0 | 0 | 46 | 215 | N/A | 0.000 | 1.000 | N/A | 0.000 | 1.000 | 0.970 | 0.831 |
| validation | 29 | 29 | 43 | 0 | 189 | 0.403 | 1.000 | 0.815 | 0.574 | 0.185 | 0.000 | 1.000 | 1.000 |

Most-confused pairs for embeddings/lr:

- timeout -> validation: 39 rows (0.85 of timeout)
- timeout -> authentication: 7 rows (0.15 of timeout)
- rate_limit -> validation: 4 rows (0.10 of rate_limit)
- rate_limit -> authentication: 2 rows (0.05 of rate_limit)

## Gain over the rules baseline

| Model | Macro-F1 gain | McNemar p | Classes worse than baseline |
|---|---|---|---|
| tfidf/linear_svc | +0.000 | 1 | none |
| embeddings/linear_svc | +0.000 | 1 | none |
| embeddings/lr | -0.010 | 1 | authentication |
| tfidf/lr | -0.011 | 0.5 | authentication, rate_limit |
| embeddings/rf | -0.372 | 3.72e-19 | authentication, dependency, rate_limit, server_error |
| tfidf/rf | -0.587 | 5.07e-29 | authentication, authorization, dependency, rate_limit, validation |

## TF-IDF vs embeddings (same model type)

| Model | TF-IDF macro-F1 | Embeddings macro-F1 | TF-IDF ECE | Embeddings ECE | McNemar p | Significant |
|---|---|---|---|---|---|---|
| lr | 0.767 | 0.768 | 0.169 | 0.117 | 0.5 | no |
| linear_svc | 0.778 | 0.778 | 0.199 | 0.226 | 1 | no |
| rf | 0.191 | 0.406 | 0.371 | 0.176 | 0.000211 | yes |

## McNemar tests (every pair)

| A | B | A right, B wrong | A wrong, B right | Statistic | p-value | Method | Significant |
|---|---|---|---|---|---|---|---|
| rules | tfidf/linear_svc | 0 | 0 | 0 | 1 | no_disagreements | no |
| rules | embeddings/linear_svc | 0 | 0 | 0 | 1 | no_disagreements | no |
| rules | embeddings/lr | 0 | 0 | 0 | 1 | no_disagreements | no |
| rules | tfidf/lr | 0 | 2 | 0 | 0.5 | exact_binomial | no |
| rules | embeddings/rf | 82 | 0 | 80 | 3.72e-19 | chi2_continuity | yes |
| rules | tfidf/rf | 127 | 0 | 125 | 5.07e-29 | chi2_continuity | yes |
| tfidf/linear_svc | embeddings/linear_svc | 0 | 0 | 0 | 1 | no_disagreements | no |
| tfidf/linear_svc | embeddings/lr | 0 | 0 | 0 | 1 | no_disagreements | no |
| tfidf/linear_svc | tfidf/lr | 0 | 2 | 0 | 0.5 | exact_binomial | no |
| tfidf/linear_svc | embeddings/rf | 82 | 0 | 80 | 3.72e-19 | chi2_continuity | yes |
| tfidf/linear_svc | tfidf/rf | 127 | 0 | 125 | 5.07e-29 | chi2_continuity | yes |
| embeddings/linear_svc | embeddings/lr | 0 | 0 | 0 | 1 | no_disagreements | no |
| embeddings/linear_svc | tfidf/lr | 0 | 2 | 0 | 0.5 | exact_binomial | no |
| embeddings/linear_svc | embeddings/rf | 82 | 0 | 80 | 3.72e-19 | chi2_continuity | yes |
| embeddings/linear_svc | tfidf/rf | 127 | 0 | 125 | 5.07e-29 | chi2_continuity | yes |
| embeddings/lr | tfidf/lr | 0 | 2 | 0 | 0.5 | exact_binomial | no |
| embeddings/lr | embeddings/rf | 82 | 0 | 80 | 3.72e-19 | chi2_continuity | yes |
| embeddings/lr | tfidf/rf | 127 | 0 | 125 | 5.07e-29 | chi2_continuity | yes |
| tfidf/lr | embeddings/rf | 84 | 0 | 82 | 1.35e-19 | chi2_continuity | yes |
| tfidf/lr | tfidf/rf | 129 | 0 | 127 | 1.85e-29 | chi2_continuity | yes |
| embeddings/rf | tfidf/rf | 93 | 48 | 13.7 | 0.000211 | chi2_continuity | yes |

Rows inside one case are near-copies, so McNemar (which assumes independent rows) overstates significance; treat p-values near alpha with care and prefer the case-level intervals.

## Warnings

- rules: class timeout recall 0.00 < 0.5.
- tfidf/lr: class timeout recall 0.00 < 0.5.
- tfidf/linear_svc: class timeout recall 0.00 < 0.5.
- tfidf/rf: class authorization recall 0.00 < 0.5.
- tfidf/rf: class dependency recall 0.00 < 0.5.
- tfidf/rf: class rate_limit recall 0.00 < 0.5.
- tfidf/rf: class timeout recall 0.00 < 0.5.
- tfidf/rf: class validation recall 0.00 < 0.5.
- embeddings/lr: class timeout recall 0.00 < 0.5.
- embeddings/linear_svc: class timeout recall 0.00 < 0.5.
- embeddings/rf: class rate_limit recall 0.00 < 0.5.
- embeddings/rf: class server_error recall 0.00 < 0.5.
- embeddings/rf: class timeout recall 0.00 < 0.5.
- tfidf/linear_svc: does not beat the rules baseline (macro-F1 gain +0.000).
- embeddings/linear_svc: does not beat the rules baseline (macro-F1 gain +0.000).
- embeddings/lr: does not beat the rules baseline (macro-F1 gain -0.010).
- tfidf/lr: does not beat the rules baseline (macro-F1 gain -0.011).
- embeddings/rf: does not beat the rules baseline (macro-F1 gain -0.372).
- tfidf/rf: does not beat the rules baseline (macro-F1 gain -0.587).

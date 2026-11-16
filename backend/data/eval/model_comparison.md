# UC4 failure-class models: test-set comparison

Test split: 303 rows. Classes: authentication, authorization, dependency, rate_limit, server_error, timeout, validation. Intervals: 95% bootstrap over 32 test cases (1000 resamples, seed 42). Significance: alpha = 0.05.

- Same rows for every model: the fixed case-grouped test split (classifier_test.csv); identical class order checked.
- LinearSVC: predictions from the model itself, probabilities from its sigmoid calibration on the validation split.
- rules = most common class per HTTP status in train; it has no probabilities (probability metrics N/A).
- Embedding prediction times use the on-disk vector cache; a cold first call is slower.

## Recommendation

**tfidf/lr**. 6 models are statistically tied with the best (tfidf/linear_svc, tfidf/rf, embeddings/rf, tfidf/lr, embeddings/lr, embeddings/linear_svc): their macro-F1 intervals overlap and McNemar p >= 0.05. Picked tfidf/lr: Logistic Regression is the simplest model (one weight per feature and class), cheap to predict and easy to explain; among equally simple ones it has the lowest ECE. Its probabilities are less well calibrated (ECE 0.221 vs 0.032 for tfidf/rf): calibrate it on the validation split before showing its confidence to anyone.

It is NOT significantly better than the rules baseline (McNemar p = 1).

## Leaderboard (sorted by macro-F1)

| Model | Macro-F1 [95% CI] | Train acc | Test acc | Gap | Balanced acc | MCC | Top-2 acc | Log loss | ECE | Fit s | Predict ms / 100 rows |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf/linear_svc | 0.986 [0.945, 1.000] | 0.991 | 0.987 | +0.004 | 0.989 | 0.985 | 1.000 | 0.096 | 0.054 | 4.6 | 17.8 |
| tfidf/rf | 0.986 [0.945, 1.000] | 0.995 | 0.987 | +0.009 | 0.989 | 0.985 | 0.993 | 0.288 | 0.032 | 25.1 | 33.6 |
| embeddings/rf | 0.986 [0.945, 1.000] | 0.995 | 0.987 | +0.009 | 0.989 | 0.985 | 0.993 | 0.344 | 0.074 | 22.1 | 17.7 |
| rules | 0.982 [0.937, 1.000] | 0.986 | 0.983 | +0.002 | 0.986 | 0.981 | N/A | N/A | N/A | 0.0 | 0.1 |
| tfidf/lr | 0.982 [0.937, 1.000] | 0.986 | 0.983 | +0.002 | 0.986 | 0.981 | 0.993 | 0.310 | 0.221 | 3.3 | 18.1 |
| embeddings/lr | 0.982 [0.937, 1.000] | 0.986 | 0.983 | +0.002 | 0.986 | 0.981 | 0.990 | 0.351 | 0.252 | 1.3 | 9.5 |
| embeddings/linear_svc | 0.982 [0.937, 1.000] | 0.986 | 0.983 | +0.002 | 0.986 | 0.981 | 1.000 | 0.098 | 0.057 | 7.0 | 7.7 |

Macro-F1 without the insufficient-evidence test cases (294 rows): rules 0.981, tfidf/lr 0.981, tfidf/linear_svc 0.985, tfidf/rf 0.985, embeddings/lr 0.981, embeddings/linear_svc 0.981, embeddings/rf 0.985

## Per-class F1 (best per row in bold)

| Class | tfidf/linear_svc | tfidf/rf | embeddings/rf | rules | tfidf/lr | embeddings/lr | embeddings/linear_svc |
|---|---|---|---|---|---|---|---|
| authentication | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** |
| authorization | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** |
| dependency | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** |
| rate_limit | **0.959** | **0.959** | **0.959** | 0.948 | 0.948 | 0.948 | 0.948 |
| server_error | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** |
| timeout | **0.941** | **0.941** | **0.941** | 0.928 | 0.928 | 0.928 | 0.928 |
| validation | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** |

## One-vs-rest counts for tfidf/lr

| Class | Support | TP | FP | FN | TN | Precision | Recall | Specificity | F1 | FPR | FNR | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| authentication | 43 | 43 | 0 | 0 | 260 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| authorization | 32 | 32 | 0 | 0 | 271 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| dependency | 48 | 48 | 0 | 0 | 255 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| rate_limit | 51 | 46 | 0 | 5 | 252 | 1.000 | 0.902 | 1.000 | 0.948 | 0.000 | 0.098 | 0.995 | 0.983 |
| server_error | 49 | 49 | 0 | 0 | 254 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| timeout | 32 | 32 | 5 | 0 | 266 | 0.865 | 1.000 | 0.982 | 0.928 | 0.018 | 0.000 | 0.994 | 0.907 |
| validation | 48 | 48 | 0 | 0 | 255 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |

Most-confused pairs for tfidf/lr:

- rate_limit -> timeout: 5 rows (0.10 of rate_limit)

## Gain over the rules baseline

| Model | Macro-F1 gain | McNemar p | Classes worse than baseline |
|---|---|---|---|
| tfidf/linear_svc | +0.003 | 1 | none |
| tfidf/rf | +0.003 | 1 | none |
| embeddings/rf | +0.003 | 1 | none |
| tfidf/lr | +0.000 | 1 | none |
| embeddings/lr | +0.000 | 1 | none |
| embeddings/linear_svc | +0.000 | 1 | none |

## TF-IDF vs embeddings (same model type)

| Model | TF-IDF macro-F1 | Embeddings macro-F1 | TF-IDF ECE | Embeddings ECE | McNemar p | Significant |
|---|---|---|---|---|---|---|
| lr | 0.982 | 0.982 | 0.221 | 0.252 | 1 | no |
| linear_svc | 0.986 | 0.982 | 0.054 | 0.057 | 1 | no |
| rf | 0.986 | 0.986 | 0.032 | 0.074 | 1 | no |

## McNemar tests (every pair)

| A | B | A right, B wrong | A wrong, B right | Statistic | p-value | Method | Significant |
|---|---|---|---|---|---|---|---|
| tfidf/linear_svc | tfidf/rf | 0 | 0 | 0 | 1 | no_disagreements | no |
| tfidf/linear_svc | embeddings/rf | 0 | 0 | 0 | 1 | no_disagreements | no |
| tfidf/linear_svc | rules | 1 | 0 | 0 | 1 | exact_binomial | no |
| tfidf/linear_svc | tfidf/lr | 1 | 0 | 0 | 1 | exact_binomial | no |
| tfidf/linear_svc | embeddings/lr | 1 | 0 | 0 | 1 | exact_binomial | no |
| tfidf/linear_svc | embeddings/linear_svc | 1 | 0 | 0 | 1 | exact_binomial | no |
| tfidf/rf | embeddings/rf | 0 | 0 | 0 | 1 | no_disagreements | no |
| tfidf/rf | rules | 1 | 0 | 0 | 1 | exact_binomial | no |
| tfidf/rf | tfidf/lr | 1 | 0 | 0 | 1 | exact_binomial | no |
| tfidf/rf | embeddings/lr | 1 | 0 | 0 | 1 | exact_binomial | no |
| tfidf/rf | embeddings/linear_svc | 1 | 0 | 0 | 1 | exact_binomial | no |
| embeddings/rf | rules | 1 | 0 | 0 | 1 | exact_binomial | no |
| embeddings/rf | tfidf/lr | 1 | 0 | 0 | 1 | exact_binomial | no |
| embeddings/rf | embeddings/lr | 1 | 0 | 0 | 1 | exact_binomial | no |
| embeddings/rf | embeddings/linear_svc | 1 | 0 | 0 | 1 | exact_binomial | no |
| rules | tfidf/lr | 0 | 0 | 0 | 1 | no_disagreements | no |
| rules | embeddings/lr | 0 | 0 | 0 | 1 | no_disagreements | no |
| rules | embeddings/linear_svc | 0 | 0 | 0 | 1 | no_disagreements | no |
| tfidf/lr | embeddings/lr | 0 | 0 | 0 | 1 | no_disagreements | no |
| tfidf/lr | embeddings/linear_svc | 0 | 0 | 0 | 1 | no_disagreements | no |
| embeddings/lr | embeddings/linear_svc | 0 | 0 | 0 | 1 | no_disagreements | no |

Rows inside one case are near-copies, so McNemar (which assumes independent rows) overstates significance; treat p-values near alpha with care and prefer the case-level intervals.

## Warnings

- rules: test macro-F1 0.982 > 0.98: possible label leakage, or synthetic data that is too easy.
- tfidf/lr: test macro-F1 0.982 > 0.98: possible label leakage, or synthetic data that is too easy.
- tfidf/linear_svc: test macro-F1 0.986 > 0.98: possible label leakage, or synthetic data that is too easy.
- tfidf/rf: test macro-F1 0.986 > 0.98: possible label leakage, or synthetic data that is too easy.
- embeddings/lr: test macro-F1 0.982 > 0.98: possible label leakage, or synthetic data that is too easy.
- embeddings/linear_svc: test macro-F1 0.982 > 0.98: possible label leakage, or synthetic data that is too easy.
- embeddings/rf: test macro-F1 0.986 > 0.98: possible label leakage, or synthetic data that is too easy.
- tfidf/linear_svc: beats the rules baseline by +0.003 macro-F1, but not significantly (McNemar p = 1.000).
- tfidf/rf: beats the rules baseline by +0.003 macro-F1, but not significantly (McNemar p = 1.000).
- embeddings/rf: beats the rules baseline by +0.003 macro-F1, but not significantly (McNemar p = 1.000).
- tfidf/lr: does not beat the rules baseline (macro-F1 gain +0.000).
- embeddings/lr: does not beat the rules baseline (macro-F1 gain +0.000).
- embeddings/linear_svc: does not beat the rules baseline (macro-F1 gain +0.000).

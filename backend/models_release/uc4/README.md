# UC4 failure-class model: `tfidf/linear_svc`

Released by `scripts/release_model.py`; every number below comes from `backend/data/eval/metrics*.json`.
Full reports: `backend/data/eval/model_comparison.md`, `split_comparison.md`, `robustness.md`; plots in `backend/data/eval/plots/`.

## What it is
LinearSVC on the shared TF-IDF features (`app/uc4/ml/features.py`: cleaned message word + char TF-IDF, one-hot status /
route / error code / upstream error, scaled numbers, 0/1 flags), tuned on the train split with case-grouped folds
(best params `{'clf__C': 0.1}`). Predicts one of: authentication, authorization, dependency, rate_limit, server_error, timeout, validation.

## Why this model
`model_comparison.md` finds 6 models statistically tied on macro-F1 and its tie rule picks the simplest type (tfidf/lr). This release instead picks the tied model with the best probabilities (lowest log loss and Brier), because the pipeline shows and acts on the model's confidence.

| Tied model | Test macro-F1 | Log loss | Brier | ECE |
|---|---|---|---|---|
| tfidf/linear_svc | 0.986 | 0.096 | 0.025 | 0.054 |
| embeddings/linear_svc | 0.982 | 0.098 | 0.026 | 0.057 |
| tfidf/rf | 0.986 | 0.288 | 0.040 | 0.032 |
| tfidf/lr | 0.982 | 0.310 | 0.095 | 0.221 |
| embeddings/rf | 0.986 | 0.344 | 0.066 | 0.074 |
| embeddings/lr | 0.982 | 0.351 | 0.112 | 0.252 |

## Scores (random split)

| | Train | Test |
|---|---|---|
| Rows | 427 | 303 |
| Accuracy | 0.991 | 0.987 |
| Macro-F1 | 0.989 | 0.986 [95% CI 0.945 to 1.000] |

Test: balanced accuracy 0.989, MCC 0.985, top-2 accuracy 1.000,
log loss 0.096, Brier 0.025, ECE 0.054.

| Class | Test F1 |
|---|---|
| authentication | 1.000 |
| authorization | 1.000 |
| dependency | 1.000 |
| rate_limit | 0.959 |
| server_error | 1.000 |
| timeout | 0.941 |
| validation | 1.000 |

## Limits (read before using it)
- On message wording never seen in training (grouped split) the same model type scores
  accuracy 0.801, macro-F1 0.778: no better than predicting
  from the HTTP status code alone. See `split_comparison.md`.
- Synthetic data: the status code nearly decides the class, so high scores here say little about real logs.
- Probabilities: use the calibrated model stored next to it (`bundle["calibrated"]`); the raw LinearSVC has none.

## How to load
```python
import joblib
from app.uc4.ml.features import parse_lines

bundle = joblib.load("models_release/uc4/failure_class_tfidf__linear_svc.joblib")   # from backend; trusted file only (pickle)
X = parse_lines(["status=429 route=POST /v1/payments code=ERR_RATE_LIMITED message=Too many requests"])
label = bundle["model"].predict(X)[0]
probs = dict(zip(bundle["calibrated"].classes_, bundle["calibrated"].predict_proba(X)[0]))
```
Needs scikit-learn 1.9.1 (pinned in `requirements.txt`). File sha256: `844ed00705dc838dec8ff36fd3fb5723c945586133c9f41bcb4ed7a67e1d3922`.
Rebuild instead of trusting the file: `scripts/train_models.py --split random` (seed 42, deterministic).

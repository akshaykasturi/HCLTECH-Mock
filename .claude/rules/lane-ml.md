---
paths:
  - "backend/app/core/ml/**"
  - "backend/app/domain/steps.py"
  - "backend/scripts/tune_gate.py"
  - "backend/scripts/train.py"
---

# Lane: ML classification (owner Raswanth)

- scikit-learn only: TF-IDF (word 1-2 grams + character 3-5 grams) + LogisticRegression inside `CalibratedClassifierCV(method="sigmoid")`.
- `random_state=42` everywhere.
- Train on the train split, tune on the validation split, never make a decision from the test split.
- `predict()` returns (label, probability of that label, all probabilities). The probabilities sum to 1.
- Conformal sets: split conformal. Nonconformity = 1 - p(true class). `qhat` = the ceil((n+1)(1-alpha))/n quantile of calibration scores. `predict_set` returns every label with 1 - p <= qhat. A set with more than one label is a CLARIFY signal.
- Save the model with joblib in `backend/models/` (git-ignored). It is trained at Docker build or on first use.
- `cost_threshold` reads costs from `policy.yaml`, prints the chosen threshold and expected cost. Akshay copies the threshold into `policy.yaml`.

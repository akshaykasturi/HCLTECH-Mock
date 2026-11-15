---
paths:
  - "backend/app/pipeline/classify.py"
  - "backend/app/ml/**"
  - "backend/scripts/tune_gate.py"
  - "backend/scripts/generate_data.py"
  - "backend/scripts/scenarios.py"
  - "backend/data/historical_tickets.csv"
  - "backend/data/kb_articles.json"
  - "backend/data/DATA_CARD.md"
---

# Lane: ML classification and training data (owner Raswanth)

- scikit-learn only: TF-IDF (word 1-2 grams + character 3-5 grams) + LogisticRegression inside `CalibratedClassifierCV(method="sigmoid")`. `knn_vote` stays as the baseline.
- Seed 42 everywhere.
- Train on training data, tune on validation, never choose anything from the test sets.
- Probabilities from the classifier sum to 1; `Classification.confidence` is the probability of the chosen label.
- Conformal sets: split conformal; nonconformity = 1 - p(true class); `qhat` = the ceil((n+1)(1-alpha))/n quantile of calibration scores; the set holds every label with 1 - p <= qhat. More than one label in the set is a CLARIFY signal.
- The model is cached in `data/index/classifier.joblib` (git-ignored) and rebuilt when the data changes.
- `tune_gate.py` prints its recommended threshold; Akshay copies it into `policy.yaml`. A cost-based threshold reads its two costs from `policy.yaml`.
- After changing the data generator, update `DATA_CARD.md`.

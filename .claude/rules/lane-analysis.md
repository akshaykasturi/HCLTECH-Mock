---
paths:
  - "backend/app/core/analysis/**"
  - "backend/scripts/evaluate.py"
  - "backend/data/eval/**"
  - "docs/pitch/**"
  - "docs/DEMO-SCRIPT.md"
---

# Lane: maths analysis, evaluation report, pitch (owner Akhilesh)

- numpy only (scipy.stats if it is already installed). Pure functions: arrays in, floats or dicts of floats out.
- Calibration: ECE with 10 equal-width bins; Brier score = mean squared error of the predicted probability (one-vs-rest for many classes; say so in the docstring).
- Bootstrap: resample with replacement, seed 0, 2000 rounds; return (point, low, high).
- McNemar: exact binomial test when b + c < 25, otherwise chi-square with continuity correction.
- Every metric in the report shows value, 95% confidence interval, sample size, and the baseline beside it.
- `evaluate.py` imports metric functions from their owners (`core/retrieval/metrics.py`, `core/evals/rag.py`, `core/analysis/`). It never copies them.
- `evaluate.py` writes `data/eval_report.json` and `docs/eval_report.md`. The README, pitch and demo quote numbers from this file only.
- Eval sets in `data/eval/` with a `README.md` saying where each split came from and its size.

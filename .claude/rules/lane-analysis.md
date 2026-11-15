---
paths:
  - "backend/app/analysis/**"
  - "backend/scripts/evaluate.py"
  - "backend/data/test/**"
  - "backend/data/validation/**"
  - "docs/pitch/**"
  - "docs/DEMO-SCRIPT.md"
---

# Lane: evaluation, maths analysis, pitch

- numpy only (scipy.stats if it is already installed). Pure functions: arrays in, floats or dicts out.
- Calibration: ECE (already in evaluate.py) plus Brier score. Bootstrap: resample with replacement, seed 0, 2000 rounds, return (point, low, high). McNemar: exact binomial test when b + c < 25, else chi-square with continuity correction.
- `evaluate.py` reports each test source separately and shows every metric with its sample size and baseline (kNN, majority class); add 95% confidence intervals from `analysis/stats.py`.
- Import metric functions from `evals/answers.py` and `analysis/`; don't copy them.
- Test sets are never used to choose a threshold or a model. The validation set is for tuning only.
- The README, pitch and demo quote numbers from `docs/eval_report.md` only.

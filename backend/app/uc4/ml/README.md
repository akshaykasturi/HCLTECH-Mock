# UC4 ML: shared features

`features.py` turns a failing log line into numbers that any scikit-learn classifier can use.
Every classifier uses the same cleaning, the same columns and the same train/test rows, so scores are comparable.

- `clean_text(s)`: masks tokens, keys, JWTs, emails, IPs, UUIDs, request/correlation IDs, timestamps, hex and long numbers (`<IP>`, `<NUM>`, ...); lowercases; keeps codes like `err_auth_token_expired`, `invalid_token`, `401`.
- `parse_lines(lines)`: one raw line (`status=.. route=.. code=.. message=..`) to the columns listed in `CONFIG`.
- `build_features(mode="default" | "nb", **overrides)`: an **unfitted** `ColumnTransformer`. Use `"nb"` for MultinomialNB / ComplementNB (all values >= 0).
- `get_split()`: the team's fixed split, grouped by case (`classifier_train.csv` / `classifier_test.csv`). Same rows every call.
- `get_validation()`: the validation split (`classifier_calibration.csv`), for tuning only.
- `get_groups("train")`: case IDs for `GroupKFold`. Use them when cross-validating: rows from one case are near-copies.

Columns live in `CONFIG` at the top of `features.py`; change them there, not in code.
Transformer names for `GridSearchCV`: `text_word`, `text_char`, `cat`, `num`, `num_log`, `bool`
(for example `features__text_word__ngram_range`).

Inspect the features: in `backend`, `.\.venv\Scripts\python.exe scripts\inspect_features.py`.

## How to plug a classifier

```python
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from app.uc4.ml.features import build_features, get_groups, get_split

X_train, X_test, y_train, y_test = get_split()
model = Pipeline([("features", build_features()), ("clf", LinearSVC())])  # Naive Bayes: build_features("nb")
model.fit(X_train, y_train)
print("f1_macro:", f1_score(y_test, model.predict(X_test), average="macro"))
```

Tuning: `GridSearchCV(model, {"features__text_word__ngram_range": [(1, 1), (1, 2)]}, cv=GroupKFold(5), scoring="f1_macro").fit(X_train, y_train, groups=get_groups("train"))`.
Never tune on the test split, and don't commit fitted models.

Note: the HTTP status nearly decides the class (only 499 and 504 are shared by rate_limit and timeout), so expect high class scores. Report them with bootstrap intervals from `app/analysis/stats.py`.

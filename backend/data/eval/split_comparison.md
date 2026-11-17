# Random vs template-grouped split

**random**: the fixed case-grouped split. All 303 test rows use a message template that also appears in train.
**grouped**: one message template per class held out (`backend/data/splits/test_idx_grouped.json`, 261 test rows); every test row uses wording never seen in training.
**rotation**: 3 rounds, a different template per class held out each round; mean and range of macro-F1.
Intervals: 95% bootstrap over test cases. Status code and error code stay visible in every mode.

## Macro-F1 by split

| Model | Random macro-F1 [95% CI] | Random train / test acc | Grouped macro-F1 [95% CI] | Grouped train / test acc | Macro-F1 drop | Rotation macro-F1 mean (min to max) |
|---|---|---|---|---|---|---|
| tfidf/linear_svc | 0.986 [0.945, 1.000] | 0.991 / 0.987 | 0.778 [0.704, 0.828] | 1.000 / 0.801 | -0.208 | 0.846 (0.775 to 0.985) |
| tfidf/rf | 0.986 [0.945, 1.000] | 0.995 / 0.987 | 0.191 [0.149, 0.242] | 1.000 / 0.314 | -0.795 | 0.307 (0.191 to 0.464) |
| embeddings/rf | 0.986 [0.945, 1.000] | 0.995 / 0.987 | 0.406 [0.308, 0.495] | 1.000 / 0.487 | -0.579 | 0.334 (0.179 to 0.415) |
| rules | 0.982 [0.937, 1.000] | 0.986 / 0.983 | 0.778 [0.704, 0.828] | 0.990 / 0.801 | -0.204 | 0.921 (0.778 to 1.000) |
| tfidf/lr | 0.982 [0.937, 1.000] | 0.986 / 0.983 | 0.767 [0.678, 0.827] | 1.000 / 0.808 | -0.215 | 0.885 (0.767 to 0.985) |
| embeddings/lr | 0.982 [0.937, 1.000] | 0.986 / 0.983 | 0.768 [0.684, 0.820] | 1.000 / 0.801 | -0.214 | 0.914 (0.768 to 0.988) |
| embeddings/linear_svc | 0.982 [0.937, 1.000] | 0.986 / 0.983 | 0.778 [0.704, 0.828] | 1.000 / 0.801 | -0.204 | 0.911 (0.778 to 0.988) |

Held-out templates per rotation round:

- round 0 (261 rows): authentication: `unauthorized`; authorization: `forbidden`; dependency: `upstream <SVC>: tls handshake with <SVC> failed: certificate has expired`; rate_limit: `too many requests`; server_error: `typeerror: cannot read properties of undefined (reading <Q>)`; timeout: `client closed request`; validation: `request validation failed`
- round 1 (353 rows): authentication: `bearer token expired`; authorization: `token lacks required scope <Q>`; dependency: `dependency <SVC> unavailable: connection refused`; rate_limit: `rate limit of <V> requests/minute exceeded for api key`; server_error: `internal server error`; timeout: `upstream <SVC> did not respond within <V> ms`; validation: `field <Q> is required`
- round 2 (261 rows): authentication: `api key not recognised for this environment`; authorization: `source ip <V> is not allowlisted for this account`; dependency: `service unavailable`; rate_limit: `too many requests`; server_error: `timed out acquiring db connection: pool exhausted (max=<V>, waiting=<V>)`; timeout: `gateway timeout`; validation: `content-type <Q> is not supported; use application/json`

## Grouped split: recommendation and warnings

**embeddings/lr**. 4 models are statistically tied with the best (tfidf/linear_svc, embeddings/linear_svc, embeddings/lr, tfidf/lr): their macro-F1 intervals overlap and McNemar p >= 0.05. Picked embeddings/lr: Logistic Regression is the simplest model (one weight per feature and class), cheap to predict and easy to explain; among equally simple ones it has the lowest ECE.

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

## Robustness (random split)

Perturbed test lines, trained models unchanged. Cells: accuracy (share of predictions that flipped).

| Model | original | ids_numbers | typos | paraphrase | no_status_code | paraphrase_no_status |
|---|---|---|---|---|---|---|
| rules | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.162 (84%) | 0.162 (84%) |
| tfidf/lr | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.881 (10%) | 0.525 (46%) |
| tfidf/linear_svc | 0.987 (0%) | 0.987 (0%) | 0.987 (0%) | 0.987 (0%) | 0.974 (1%) | 0.525 (46%) |
| tfidf/rf | 0.987 (0%) | 0.987 (0%) | 0.960 (3%) | 0.578 (42%) | 0.987 (0%) | 0.356 (64%) |
| embeddings/lr | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.446 (54%) | 0.366 (62%) |
| embeddings/linear_svc | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.406 (58%) | 0.366 (62%) |
| embeddings/rf | 0.987 (0%) | 0.987 (0%) | 0.944 (4%) | 0.828 (17%) | 0.987 (0%) | 0.607 (39%) |

Retrained without columns (test accuracy):

| Model | full | no status+code | text only |
|---|---|---|---|
| tfidf/lr | 0.983 | 0.970 | 0.983 |
| tfidf/linear_svc | 0.987 | 0.983 | 0.983 |
| tfidf/rf | 0.987 | 0.987 | 0.987 |
| embeddings/lr | 0.983 | 0.861 | 0.967 |
| embeddings/linear_svc | 0.983 | 0.970 | 0.967 |
| embeddings/rf | 0.987 | 0.987 | 0.987 |

## Robustness (grouped split)

Perturbed test lines, trained models unchanged. Cells: accuracy (share of predictions that flipped).

| Model | original | ids_numbers | typos | paraphrase | no_status_code | paraphrase_no_status |
|---|---|---|---|---|---|---|
| rules | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.111 (69%) | 0.111 (69%) |
| tfidf/lr | 0.808 (0%) | 0.808 (0%) | 0.808 (2%) | 0.801 (5%) | 0.402 (41%) | 0.295 (56%) |
| tfidf/linear_svc | 0.801 (0%) | 0.801 (0%) | 0.805 (3%) | 0.801 (0%) | 0.418 (38%) | 0.295 (51%) |
| tfidf/rf | 0.314 (0%) | 0.314 (0%) | 0.395 (12%) | 0.360 (18%) | 0.314 (0%) | 0.130 (36%) |
| embeddings/lr | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.801 (3%) | 0.467 (33%) | 0.467 (37%) |
| embeddings/linear_svc | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.406 (39%) | 0.406 (39%) |
| embeddings/rf | 0.487 (0%) | 0.487 (0%) | 0.429 (17%) | 0.437 (56%) | 0.418 (7%) | 0.341 (56%) |

Retrained without columns (test accuracy):

| Model | full | no status+code | text only |
|---|---|---|---|
| tfidf/lr | 0.808 | 0.322 | 0.264 |
| tfidf/linear_svc | 0.801 | 0.418 | 0.264 |
| tfidf/rf | 0.314 | 0.176 | 0.130 |
| embeddings/lr | 0.801 | 0.460 | 0.241 |
| embeddings/linear_svc | 0.801 | 0.460 | 0.241 |
| embeddings/rf | 0.487 | 0.418 | 0.548 |

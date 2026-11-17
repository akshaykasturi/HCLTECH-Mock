# UC4 robustness checks (random split)

Reporting only: nothing here was used to choose a model. Accuracy / macro-F1.

## Check 1: retrain with columns removed

Same hyperparameters as the tuned models; only the input columns change.

| Model | Full: val / test acc | No status+code: val / test acc | Text only: val / test acc | Text only: test macro-F1 |
|---|---|---|---|---|
| tfidf/lr | 0.992 / 0.983 | 0.992 / 0.970 | 0.992 / 0.983 | 0.982 |
| tfidf/linear_svc | 1.000 / 0.987 | 1.000 / 0.983 | 0.992 / 0.983 | 0.982 |
| tfidf/rf | 1.000 / 0.987 | 1.000 / 0.987 | 1.000 / 0.987 | 0.986 |
| embeddings/lr | 0.992 / 0.983 | 0.857 / 0.861 | 0.992 / 0.967 | 0.963 |
| embeddings/linear_svc | 0.992 / 0.983 | 0.992 / 0.970 | 0.992 / 0.967 | 0.963 |
| embeddings/rf | 1.000 / 0.987 | 1.000 / 0.987 | 1.000 / 0.987 | 0.986 |

Rules baseline (status only), for reference: val 0.992 / test 0.983.

## Check 3: perturbed test lines (trained models, unchanged)

Cells: accuracy (share of predictions that flipped vs the original lines).

| Model | Original | ids_numbers | typos | paraphrase | no_status_code | paraphrase_no_status |
|---|---|---|---|---|---|---|
| rules | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.162 (84%) | 0.162 (84%) |
| tfidf/lr | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.881 (10%) | 0.525 (46%) |
| tfidf/linear_svc | 0.987 (0%) | 0.987 (0%) | 0.987 (0%) | 0.987 (0%) | 0.974 (1%) | 0.525 (46%) |
| tfidf/rf | 0.987 (0%) | 0.987 (0%) | 0.960 (3%) | 0.578 (42%) | 0.987 (0%) | 0.356 (64%) |
| embeddings/lr | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.446 (54%) | 0.366 (62%) |
| embeddings/linear_svc | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.983 (0%) | 0.406 (58%) | 0.366 (62%) |
| embeddings/rf | 0.987 (0%) | 0.987 (0%) | 0.944 (4%) | 0.828 (17%) | 0.987 (0%) | 0.607 (39%) |

Example changes (original -> changed):

- **ids_numbers**: `status=403 route=GET /v1/orders/{id} code=ERR_FORBIDDEN_SCOPE message=Token lacks required scope 'orders:read'`
  -> `status=403 route=GET /v1/orders/{id} code=ERR_FORBIDDEN_SCOPE message=Token lacks required scope 'orders:read'`
- **typos**: `status=415 route=POST /v1/refunds code=ERR_UNSUPPORTED_MEDIA_TYPE message=Content-Type 'application/xml' is not supported; use application/json`
  -> `status=415 route=POST /v1/refunds code=ERR_UNSUPPORTED_MEDIA_TYPE message=Content-Type a'pplication/xml' is not supported; use application/josn`
- **paraphrase**: `status=429 route=POST /v1/payments code=ERR_RATE_LIMITED message=Rate limit of 100 requests/minute exceeded for API key has_retry_after ratelimit_remaining=0`
  -> `status=429 route=POST /v1/payments code=ERR_RATE_LIMITED message=quota of 100 calls per minute used up for this credential has_retry_after ratelimit_remaining=0`
- **no_status_code**: `status=503 route=GET /v1/inventory/{sku} code=ERR_DEPENDENCY_UNAVAILABLE message=Dependency inventory-db unavailable: connection refused upstream_error=connection_refused`
  -> `status=000 route=GET /v1/inventory/{sku} code=none message=Dependency inventory-db unavailable: connection refused upstream_error=connection_refused`
- **paraphrase_no_status**: `status=500 route=GET /v1/orders/{id} code=ERR_INTERNAL message=TypeError: Cannot read properties of undefined (reading 'lineItems')`
  -> `status=000 route=GET /v1/orders/{id} code=none message=null reference while accessing lineItems`

Majority-class accuracy on test: 0.168.


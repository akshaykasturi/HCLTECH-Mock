# UC4 robustness checks (grouped split)

Reporting only: nothing here was used to choose a model. Accuracy / macro-F1.

## Check 1: retrain with columns removed

Same hyperparameters as the tuned models; only the input columns change.

| Model | Full: val / test acc | No status+code: val / test acc | Text only: val / test acc | Text only: test macro-F1 |
|---|---|---|---|---|
| tfidf/lr | - / 0.808 | - / 0.322 | - / 0.264 | 0.209 |
| tfidf/linear_svc | - / 0.801 | - / 0.418 | - / 0.264 | 0.209 |
| tfidf/rf | - / 0.314 | - / 0.176 | - / 0.130 | 0.039 |
| embeddings/lr | - / 0.801 | - / 0.460 | - / 0.241 | 0.168 |
| embeddings/linear_svc | - / 0.801 | - / 0.460 | - / 0.241 | 0.209 |
| embeddings/rf | - / 0.487 | - / 0.418 | - / 0.548 | 0.410 |

Rules baseline (status only), for reference: val - / test 0.801.

## Check 3: perturbed test lines (trained models, unchanged)

Cells: accuracy (share of predictions that flipped vs the original lines).

| Model | Original | ids_numbers | typos | paraphrase | no_status_code | paraphrase_no_status |
|---|---|---|---|---|---|---|
| rules | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.111 (69%) | 0.111 (69%) |
| tfidf/lr | 0.808 (0%) | 0.808 (0%) | 0.808 (2%) | 0.801 (5%) | 0.402 (41%) | 0.295 (56%) |
| tfidf/linear_svc | 0.801 (0%) | 0.801 (0%) | 0.805 (3%) | 0.801 (0%) | 0.418 (38%) | 0.295 (51%) |
| tfidf/rf | 0.314 (0%) | 0.314 (0%) | 0.395 (12%) | 0.360 (18%) | 0.314 (0%) | 0.130 (36%) |
| embeddings/lr | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.801 (3%) | 0.467 (33%) | 0.467 (37%) |
| embeddings/linear_svc | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.801 (0%) | 0.406 (39%) | 0.406 (39%) |
| embeddings/rf | 0.487 (0%) | 0.487 (0%) | 0.429 (17%) | 0.437 (56%) | 0.418 (7%) | 0.341 (56%) |

Example changes (original -> changed):

- **ids_numbers**: `status=499 route=POST /v1/orders code=none message=client closed request`
  -> `status=499 route=POST /v1/orders code=none message=client closed request`
- **typos**: `status=502 route=POST /v1/orders code=ERR_BAD_GATEWAY message=Upstream payments-svc: TLS handshake with bank-gateway failed: certificate has expired upstream_error=tls_handshake_failed`
  -> `status=502 route=POST /v1/orders code=ERR_BAD_GATEWAY message=Upstream payments-sv:c TLS handshake with bank-gateway failed: certificate has expirde upstream_error=tls_handshake_failed`
- **paraphrase**: `status=502 route=POST /v1/payments code=ERR_BAD_GATEWAY message=Upstream bank-gateway: TLS handshake with bank-gateway failed: certificate has expired upstream_error=tls_handshake_failed`
  -> `status=502 route=POST /v1/payments code=ERR_BAD_GATEWAY message=secure channel from bank-gateway to bank-gateway broke, cert out of date upstream_error=tls_handshake_failed`
- **no_status_code**: `status=400 route=POST /v1/orders code=ERR_VALIDATION message=Request validation failed`
  -> `status=000 route=POST /v1/orders code=none message=Request validation failed`
- **paraphrase_no_status**: `status=499 route=POST /v1/orders code=none message=client closed request`
  -> `status=000 route=POST /v1/orders code=none message=caller hung up before the reply`

Majority-class accuracy on test: 0.184.


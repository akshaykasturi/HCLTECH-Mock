# Data card: UC4 synthetic API-failure dataset ("NovaPay Commerce API")

**Fully synthetic.** NovaPay is a fictional company. No real customers, keys or traffic. Licence: CC0. Generator: `scripts/generate_uc4.py` (version `uc4-gen-1.0`, seed 42). Regenerating with the same seed gives byte-identical files; `manifest.json` stores the SHA-256 of every generated file and `tests/domain/test_uc4_dataset.py` checks it.

> **In this repo:** `scripts/generate_uc4.py`, `scripts/validate_uc4.py`, `app/domains/api_failures/policy.yaml`, `evidence.py`, `casestore.py` and `tests/domain/test_uc4_dataset.py` are not committed yet: they are being handed to Akshay for the domain pack. The `observe` step (and its test) goes to Raswanth for `domain/steps.py`. `manifest.json` is unchanged, so its paths are relative to the original single `uc4/` folder; `backend/data/eval/README.md` maps them to the paths below.

## What is in it

| Path | Format | Content | Size |
|---|---|---|---|
| `backend/data/raw/uc4/api_docs/` | Markdown (front matter), 1 HTML, 1 PDF | API reference: auth, scopes, IP allowlists, rate limits, timeouts and retries, error codes, troubleshooting, architecture, changelog, endpoints, SLA; one **deprecated** doc (`legacy/rate-limits-v1.md`, 60/min) that conflicts with the current 100/min | 18 files, 55 sections |
| `backend/data/raw/uc4/logs/requests.jsonl` | JSONL | Raw gateway request logs: route, status, latency, headers, error code/message, auth details, payload *shape*, upstream info | 6,051 lines |
| `backend/data/raw/uc4/metrics/metrics.csv` | CSV | Per-minute `rps`, `error_rate`, `p50_ms`, `p95_ms` for the route and its dependencies, 60 min before to 10 min after each case | 14,200 rows |
| `backend/data/raw/uc4/changes/changes.jsonl` | JSONL | Deploys and config changes, including unrelated background changes | 114 events |
| `backend/data/eval/uc4/cases.jsonl` | JSONL | 90 labelled cases (below) | 90 |
| `backend/data/eval/uc4/classifier_{train,calibration,test}.csv` | CSV `case_id,is_focal,text,label` | Up to 12 failing lines per case for the failure-class classifier, grouped by case so no case spans two splits | 427 / 133 / 303 rows |
| `backend/data/eval/uc4/derived/` | written by `scripts/validate_uc4.py` (being handed to Akshay) | `observations.jsonl`, `likelihoods.learned.yaml`, `baseline_report.md` | |

## How labels are made

The generator first **picks the cause**, then writes raw logs, metrics and changes that this cause would produce. The label is the injected cause; nothing is labelled after the fact, and the `observe` step never reads labels (test: `test_observe_does_not_read_labels`).

- **14 causes in 7 classes** (from `app/domains/api_failures/policy.yaml`, being handed to Akshay for the domain pack): authentication (token_expired, invalid_api_key), authorization (missing_scope, ip_not_allowlisted), validation (missing_required_field, unsupported_media_type), rate_limit (client_rate_limit_exceeded, retry_storm), timeout (upstream_dependency_slow, client_timeout_too_low), dependency (dependency_outage, upstream_tls_failure), server_error (deployment_regression, db_pool_exhausted).
- **6 cases per cause:** 2 easy, 2 medium, 2 hard.
  - *Easy:* every expected signal, specific error code, no red herrings.
  - *Medium:* each signal kept with its probability; red herrings possible.
  - *Hard:* signals kept at 0.7× probability; generic error code 75% of the time (e.g. `ERR_INTERNAL`, `ERR_FORBIDDEN`); red herrings at 2× probability (e.g. an unrelated deploy during a pool-exhaustion incident). Every labelled case keeps at least its strongest signal.
- **6 insufficient-evidence cases** (`expected_cause: null`, `expected_outcome: CLARIFY`, with `missing_info`): missing endpoint metrics, missing dependency metrics, 401 without auth details, one isolated 504, 429 without rate-limit headers, a single 500 with no other requests.
- Each case records how it was made in `generation`: signals on, signals dropped, red herrings, whether the error code was specific.

## Case fields

`case_id, split, difficulty, focal_correlation_id, route, onset_ts, window_start, window_end, expected_class, expected_cause, expected_first_check` (the cause's verify step from the catalog), `expected_outcome` (RECOMMEND / CLARIFY), `requires_escalation, culprit_dependency, culprit_client, missing_info, worked_example, human_verify_suggested, summary, generation`.

## Splits

Per cause: train = 1 easy + 1 medium + 1 hard; calibration = 1 medium; test = 1 easy + 1 hard. Insufficient cases: 1 train, 1 calibration, 4 test. Totals: **43 train / 15 calibration / 32 test.** In this repo "calibration" is the **validation** split; case lists are in `backend/data/eval/uc4/splits/`.

## Worked examples (the brief asks for at least five)

| Case | Covers | Focal correlation ID |
|---|---|---|
| UC4-0026 | 4xx: 400 missing required field (payments) | c-91a2195d1f |
| UC4-0074 | 5xx: 500 after a deploy (orders) | c-38110e7288 |
| UC4-0002 | Authentication: 401 expired token | c-1752f5d560 |
| UC4-0050 | Timeout: 504 slow dependency | c-1e93f5b875 |
| UC4-0038 | Rate limiting: 429 client over 100/min | c-8f4e3a51a3 |

Plus a refusal-style example: any of UC4-0087 to UC4-0090 (test split, CLARIFY).

## Sensitive data, on purpose

Raw logs contain **fake** credentials and PII so redaction can be tested: 3,056 bearer tokens (JWT-shaped), 2,923 `nvp_live_` keys, 72 `nvp_test_` keys, 38 echoed customer emails (`@example.com/.org/.net`), and client IPs from the documentation ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24). `evidence.py` masks them structurally; `validate_uc4.py` scans all evidence for every pattern (0 leaks). (Both are being handed to Akshay for the domain pack.)

## Baseline (naive Bayes on the observations, `backend/data/eval/uc4/derived/baseline_report.md`)

| Likelihoods | Test top-1 cause | Test top-3 | MRR | Class accuracy |
|---|---|---|---|---|
| Expert (policy.yaml) | 0.93 | 1.00 | 0.96 | 1.00 |
| Learned from train split | 0.93 | 1.00 | 0.96 | 1.00 |

Remaining confusions are the realistic ones: retry_storm vs client_rate_limit_exceeded, db_pool_exhausted vs deployment_regression. The missing-evidence rule (`hypotheses.clarify_if_any` in policy.yaml) flags 6/6 insufficient cases and 0/84 labelled cases. Naive Bayes alone stays overconfident on them (max posterior 0.62–0.99), which is why that rule exists.

## Known limitations (say these on stage)

- **Class is easy, cause is the real task.** HTTP status nearly determines the failure class (class accuracy 1.00). Ranking the cause within a class is where the models are tested.
- **Small test set.** 28 labelled test cases: report bootstrap confidence intervals, not bare percentages.
- **The generator and the likelihoods share assumptions.** The expert likelihoods were written by the same team that wrote the generator. Report learned and expert likelihoods side by side, and hand-check the 18 `human_verify_suggested` cases (14 hard + 4 insufficient, all in test).
- **Simplified world.** One region and one gateway per request; metrics only around incidents; no multi-cause incidents; clean timestamps.

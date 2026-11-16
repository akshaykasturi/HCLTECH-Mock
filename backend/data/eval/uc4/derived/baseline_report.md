# UC4 dataset validation report

Cases: 90; consistency failures: 0.

## Raw secrets present on purpose (redaction tests)

| Kind | Count in logs/requests.jsonl |
|---|---|
| bearer_tokens | 3056 |
| live_keys | 2923 |
| test_keys | 72 |
| emails_in_messages | 38 |

Evidence built by `evidence.py` was scanned for all of these: 0 leaks.

## Naive-Bayes baseline (cause ranking)

Expert = likelihoods in policy.yaml. Learned = estimated from the train split (Laplace).

| Likelihoods | Split | n | Top-1 cause | Top-3 cause | MRR | Class accuracy |
|---|---|---|---|---|---|---|
| expert | calibration | 14 | 0.93 | 1.00 | 0.96 | 1.00 |
| expert | test | 28 | 0.93 | 1.00 | 0.96 | 1.00 |
| learned | calibration | 14 | 0.93 | 1.00 | 0.96 | 1.00 |
| learned | test | 28 | 0.93 | 1.00 | 0.96 | 1.00 |

Most common top-1 confusions on test (true -> predicted):

- expert: retry_storm -> client_rate_limit_exceeded (2)
- learned: retry_storm -> client_rate_limit_exceeded (1); db_pool_exhausted -> deployment_regression (1)

Max posterior on the 6 insufficient-evidence cases (lower is better; the gate should CLARIFY):

- expert: [0.86, 0.95, 0.62, 0.99, 0.86, 0.93]
- learned: [0.85, 0.24, 0.37, 0.9, 0.61, 0.87]

## Key-signal coverage (share of cases where the cause's main signal is observed)

| Cause | easy | medium | hard |
|---|---|---|---|
| token_expired | 2/2 | 2/2 | 2/2 |
| invalid_api_key | 2/2 | 1/2 | 2/2 |
| missing_scope | 2/2 | 2/2 | 2/2 |
| ip_not_allowlisted | 2/2 | 2/2 | 2/2 |
| missing_required_field | 2/2 | 2/2 | 2/2 |
| unsupported_media_type | 2/2 | 2/2 | 2/2 |
| client_rate_limit_exceeded | 2/2 | 2/2 | 2/2 |
| retry_storm | 2/2 | 1/2 | 1/2 |
| upstream_dependency_slow | 2/2 | 1/2 | 1/2 |
| client_timeout_too_low | 2/2 | 2/2 | 0/2 |
| dependency_outage | 2/2 | 2/2 | 2/2 |
| upstream_tls_failure | 2/2 | 2/2 | 1/2 |
| deployment_regression | 2/2 | 2/2 | 1/2 |
| db_pool_exhausted | 2/2 | 2/2 | 1/2 |

Hard cases deliberately drop signals and add red herrings, so coverage below 100% there is by design.

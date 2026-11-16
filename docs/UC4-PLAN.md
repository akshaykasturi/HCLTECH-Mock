# UC4 build plan: API failure diagnosis

The problem we are solving now. Every teammate's Claude reads this before any UC4 task.
The ticket app (`backend/app/pipeline/`, `main.py` endpoints, current screens) stays as it is: UC4 is built next to it.

## What the brief asks for

Input: an API failure case. Using request logs, endpoint metrics, error messages and API docs, return:

- a failure classification (one of 7 classes);
- correlated evidence (log lines, metric changes, deploys, doc sections), each with its source;
- ranked likely causes, each with **supporting and contradicting** evidence;
- a confidence, and the information that is missing;
- safe, non-destructive verification steps; **escalate** when a step needs privileged access.

Hard rules: a probable cause is never shown as confirmed. Secrets are never shown.
FR-08: an audit-friendly report the reviewer can confirm, reject or annotate.
Submission: working app, evaluation report, 5 worked examples (4xx, 5xx, auth, timeout, rate limit), README.

## 1. The flow

```
case -> mask secrets -> evidence -> observe -> classify -> rank causes -> gate -> LLM report -> output checks -> API + screen + feedback
                                                                            |
                                                                            +-> CLARIFY + missing info (no LLM call)
evaluation runs the same diagnose() over the validation and test splits
```

| Step | What it does | File |
|---|---|---|
| case | Load a case by `case_id` from `cases.jsonl` (route, `focal_correlation_id`, `onset_ts`, window) | `uc4/casestore.py` |
| mask secrets | Mask bearer tokens, `nvp_live_`/`nvp_test_` keys, emails and client IPs before anything else reads the text | `uc4/safety.py` |
| evidence | Log lines in the case window; metrics for the route and its dependencies compared with the hour before onset; deploys and config changes near onset; doc search over the API docs | `uc4/evidence.py` |
| observe | Turn evidence into yes/no signals (`status_401`, `token_age_over_ttl`, `dep_latency_spike`, `recent_deploy`, `metrics_missing`...). Never reads labels | `uc4/observe.py` |
| classify | Failure class (authentication, authorization, validation, rate_limit, timeout, dependency, server_error) | `uc4/observe.py` or a classifier trained on `classifier_*.csv` |
| rank causes | Naive Bayes: prior x likelihood of each signal per cause, likelihoods from `uc4/policy.yaml`. Each cause lists the signals that support it and the ones that contradict it | `uc4/rank.py` |
| gate | `clarify_if_any` rule in policy.yaml: not enough evidence -> CLARIFY with `missing_info`, no LLM call. A cause whose check needs privileged access -> ESCALATE | `uc4/rank.py` or `uc4/pipeline.py` |
| LLM report | The LLM writes the words only, from the ranked causes and evidence ids it is given; extractive fallback without LLM | `uc4/report.py` (via `app.llm.router.run_llm`) |
| output checks | Citations exist word for word; every number appears in the evidence; no "confirmed"/"root cause is" unless backed; no destructive steps; no secrets | `uc4/safety.py` |
| pipeline | `diagnose(case_id, llm) -> Diagnosis`: runs the steps in order, writes an audit trail of every step | `uc4/pipeline.py` |
| API + screen | `POST /api/diagnose` (by case id), a case list, report screen with confirm / reject / note | `main.py`, `frontend/` |
| evaluation | Top-1, top-3, MRR, class accuracy, CLARIFY rate, bootstrap CIs | `backend/scripts/evaluate_uc4.py` |

Same design rule as always: code decides the class, the ranking, the outcome and the confidence. The LLM only writes the report. Code checks the report before anyone sees it.

## 2. Where everything lives

- Raw data: `backend/data/raw/uc4/` (`api_docs/`, `logs/requests.jsonl`, `metrics/metrics.csv`, `changes/changes.jsonl`).
- Labelled data: `backend/data/eval/uc4/` (`cases.jsonl`, `classifier_{train,calibration,test}.csv`, `splits/`, `retrieval_gold.jsonl`, `derived/`). Read `backend/data/eval/uc4/DATA_CARD.md` first.
- Code: new package `backend/app/uc4/` with `__init__.py`, `contracts.py`, `casestore.py`, `evidence.py`, `observe.py`, `policy.yaml`, `rank.py`, `pipeline.py`, `safety.py`, `report.py`.
- Scripts: `backend/scripts/` (`generate_uc4.py`, `validate_uc4.py`, `evaluate_uc4.py`).
- Tests: `backend/tests/test_uc4_<name>.py`. Offline like all tests: no real LLM, no network.
- UC4 code may import helpers from the ticket app (`app.llm.router`, `app.pipeline.retrieve`, `app.pipeline.redact`) but does not change them.

## 3. Who leads what

Lead = who knows it best and builds it first. Anyone can work on any file.

| Person | Leads |
|---|---|
| Akshay | `uc4/contracts.py`, `evidence.py` and doc search, `rank.py`, the gate, `pipeline.py` (`diagnose()`), merges |
| Atheesha | `uc4/safety.py` (masking + output checks: citations, numbers, no unsupported "confirmed", no destructive steps, no secrets), `uc4/report.py` (LLM report + fallback), red-team cases in `backend/data/redteam/uc4/` |
| Raswanth | `uc4/observe.py` (yes/no signals) and the failure-class classifier on `classifier_*.csv`, calibrated on the validation split |
| Akhilesh | Dataset and generator code (`generate_uc4.py`, `validate_uc4.py`), `evaluate_uc4.py` and `docs/uc4_eval_report.md`, the 5 worked examples, pitch |
| Roshan | Doc loaders (Markdown with front matter, HTML, PDF), `POST /api/diagnose` and a case list endpoint, report screen with confirm / reject / note feedback |

## 4. Rules that keep the pieces fitting

- **Use the data's own field names.** Logs: `ts`, `correlation_id`, `route`, `status`, `latency_ms`, `client_id`, `error`, `auth`, `upstream`. Metrics: `ts`, `kind` (`endpoint` / `service`), `target`, `rps`, `error_rate`, `p50_ms`, `p95_ms`. Cases: `case_id`, `focal_correlation_id`, `onset_ts`, `window_start`, `window_end`. Don't rename them.
- **One cause catalog only:** `backend/app/uc4/policy.yaml` (14 causes in 7 classes, likelihoods, verify steps, the `clarify_if_any` rule). Nobody keeps a second list of causes in code.
- **Shared shapes** live in `backend/app/uc4/contracts.py`. Import them; don't redefine them.
- **Splits:** train for training, validation (the files call it "calibration") for tuning, test only for final numbers. Never choose a threshold, prior or likelihood by looking at test results.
- **Deprecated docs are never cited as current.** `legacy/rate-limits-v1.md` (60/min) has `status: deprecated` in its front matter; the current limit is 100/min. Doc search drops or labels deprecated docs.
- **Wording:** causes are "likely" or "probable". "Confirmed" only after a reviewer confirms it in feedback.
- **Verification steps are read-only** (look at logs, headers, dashboards, docs). Anything that changes a system, or needs admin access, becomes ESCALATE.
- **Secrets:** mask before evidence leaves `evidence.py`; check again on the final output. Tests use the fake keys in the dataset, never real ones.
- **Build on, don't rewrite.** Extend someone's file instead of replacing it. If a file you need doesn't exist yet, write a simple fallback in your own file with a `# TODO: use uc4/<file> when merged` comment, and keep going.

## 5. Known gap: files the data card mentions but nobody has committed

`DATA_CARD.md` says these were "handed to Akshay" but they are not in the repo:
`generate_uc4.py`, `validate_uc4.py`, the cause catalog `policy.yaml`, `evidence.py`, `casestore.py`, the observe step and `test_uc4_dataset.py`.

**Akhilesh commits them first**, at the new paths:

| Data card path | Path in this repo |
|---|---|
| `scripts/generate_uc4.py`, `scripts/validate_uc4.py` | `backend/scripts/` |
| `app/domains/api_failures/policy.yaml`, `evidence.py`, `casestore.py` | `backend/app/uc4/` |
| observe step (`domain/steps.py`) | `backend/app/uc4/observe.py` |
| `tests/domain/test_uc4_dataset.py` | `backend/tests/test_uc4_dataset.py` |

Also: the dataset itself is on branch `data/uc4-dataset`; it must be merged into `main` before anyone builds on it.
Until these land, use the fallback rule above. `derived/observations.jsonl` and `derived/likelihoods.learned.yaml` show the expected signal names and can be used in tests.

## 6. What "done" looks like

- `POST /api/diagnose` returns class, ranked causes with supporting and contradicting evidence, confidence, missing info, safe steps and outcome for all 90 cases, offline.
- The 6 insufficient-evidence cases give CLARIFY; no labelled case does.
- No secret appears in any output (checked by a test over all 90 cases).
- `docs/uc4_eval_report.md`: test-split numbers with bootstrap CIs, next to the naive Bayes baseline in the data card.
- 5 worked examples: UC4-0026 (4xx), UC4-0074 (5xx), UC4-0002 (auth), UC4-0050 (timeout), UC4-0038 (rate limit), plus one CLARIFY case (UC4-0087 to UC4-0090).

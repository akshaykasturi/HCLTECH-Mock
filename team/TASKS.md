# Tasks for the mock build

Each person works through their own list in order. One task = one branch = one pull request.
Start each task in Claude Code with: `/start-task <branch> Task <id> from team/TASKS.md`

"Waits for" tells you when a task can start:
- **A** = the skeleton pull request (Prompt A) is merged. It creates every stub file and spec test.
- **B** = the port pull request (Prompt B) is merged. It moves the old working code into `core/`.
- **PS** = the problem statement for the mock is picked and Akshay has written `domain/contracts.py`.

Done when = the spec tests for that function pass with their `xfail` markers removed, plus anything listed.

## Akshay: search side + integrator

| # | Branch | Files | What to build | Done when | Waits for |
|---|---|---|---|---|---|
| A1 | `core/skeleton` | many (Prompt A) | Contracts, stubs, spec tests, fixtures, domain templates | Merged, CI green, team told to start | Kit merged |
| A2 | `core/port` | many (Prompt B) | Move old working code into `core/` and `domains/tickets/` | Old app still runs, all old tests pass | A1 |
| A3 | `core/chunking` | `core/chunking.py` | `chunk()`: split at headings, then ~220 words with 40 overlap; ids `doc#n`; heading path in metadata | Chunks of `sample_documents.json` keep headings and ids | A |
| A4 | `core/retrieval-metrics` | `core/retrieval/metrics.py` | `recall_at_k`, `mrr`, `ndcg_at_k` | Hand-checked small examples pass | A |
| A5 | `core/pipeline` | `core/pipeline.py` | `run()`: runs the domain's steps, times each, stops on `ctx.stop`, confidence = min(signals) | Tickets pack runs through `run()` end to end | B |
| A6 | `core/search-chunks` | `core/retrieval/` | Index chunks from `load_documents()` + `chunk()`; `Evidence.score` = strength 0..1 | `/api/search` returns cited chunks for the mock data | A3, R3 |
| A7 | `core/domain-contracts` | `domain/__init__.py`, `domain/contracts.py`, `domain/policy.yaml` | Input/output models and categories for the mock problem | Everyone can build domain files against it | PS |

Every 45 minutes: merge round (checklist in the team doc), then post "pull main".

## Atheesha: answer side (LLM, safety, answer quality)

| # | Branch | Files | What to build | Done when | Waits for |
|---|---|---|---|---|---|
| T1 | `ai/numbers-check` | `core/guardrails/numbers.py` | `check_numbers()`: every number in the answer must appear in its cited evidence | Flags "500 requests" when the evidence says 100 | A |
| T2 | `ai/certainty-pii` | `core/guardrails/certainty.py`, `pii_out.py` | Flag "definitely/guaranteed/confirmed" not backed by evidence; find personal data in the output | Both checks return the right findings on fixtures | A |
| T3 | `ai/llm-cache` | `core/llm/cache.py` | `get`/`put` keyed by hash of model + prompts + corpus version | Same key returns the saved answer; off in tests | A |
| T4 | `ai/gateway` | `core/llm/gateway.py`, `providers/openai_compat.py` | `generate()`: any output schema, Gemini, then Groq or Ollama (`LLM_BASE_URL`), then extractive; one repair retry | Works with the fake LLM; falls back when a provider fails | B |
| T5 | `ai/rag-evals` | `core/evals/rag.py` | `citation_precision`, `groundedness`, `number_faithfulness`, `abstention` | Hand-made run results give the expected numbers | A |
| T6 | `ai/redteam` | `scripts/redteam.py`, `data/redteam/attacks.jsonl` | About 20 attacks: prompt injection, personal data, hazards, off-topic, typos, mixed language | Prints a pass rate per category | B |
| T7 | `ai/domain-prompt` | `domain/prompts.py`, `domain/checks.py` | Prompt and domain checks for the mock problem | One real run returns checked JSON | PS, T4 |

## Raswanth: ML classification

| # | Branch | Files | What to build | Done when | Waits for |
|---|---|---|---|---|---|
| S1 | `ml/conformal` | `core/ml/conformal.py` | `fit_qhat()`, `predict_set()` (split conformal, alpha 0.1) | A clear-cut input gives a set of 1 label; an ambiguous one gives 2 or more | A |
| S2 | `ml/cost-threshold` | `core/ml/thresholds.py` | `cost_threshold()`: pick the cut-off with the lowest expected cost | Returns the known best threshold on a toy example | A |
| S3 | `ml/generic-classifier` | `core/ml/classifier.py`, `scripts/train.py` | `train()`/`predict()` from any CSV with `text,label` columns; calibrated; saved with joblib | Tickets data trains; probabilities sum to 1 | B |
| S4 | `ml/classify-step` | `domain/steps.py` | Classify step: sets category, `classifier_prob` signal, conformal set; more than 1 label gives the CLARIFY reason | Shows in a full pipeline run | A5, S1, S3 |
| S5 | `ml/tune-gate` | `scripts/tune_gate.py` | Uses `cost_threshold` on the validation set; prints a threshold for Akshay | Prints threshold + expected cost | S2, K4 |

## Akhilesh: maths analysis, evaluation report, pitch

| # | Branch | Files | What to build | Done when | Waits for |
|---|---|---|---|---|---|
| K1 | `analysis/calibration-ci` | `core/analysis/stats.py` | `calibration()` (ECE, Brier, bins), `bootstrap_ci()` | Matches hand-worked examples | A |
| K2 | `analysis/mcnemar-riskcov` | `core/analysis/stats.py` | `mcnemar()`, `risk_coverage()` | Matches hand-worked examples | K1 |
| K3 | `analysis/baselines` | `core/analysis/baselines.py` | Majority-class and keyword baselines | Toy examples pass | A |
| K4 | `analysis/eval-sets` | `data/eval/` | Train/validation/test splits for the mock problem + `README.md` (source, size, how made) | Splits saved; no overlap between them | PS, R3 |
| K5 | `analysis/evaluate` | `scripts/evaluate.py` | Report with ML, search and answer sections; each metric with CI, n and baseline; writes JSON + Markdown | `docs/eval_report.md` generated from one command | K1-K4, A4, T5 |
| K6 | `docs/pitch-demo` | `docs/pitch/`, `docs/DEMO-SCRIPT.md` | Pitch outline and a 3-minute demo script; numbers only from `eval_report.json` | Team rehearses it once | K5 |

## Roshan: data ingestion, API, database, frontend

| # | Branch | Files | What to build | Done when | Waits for |
|---|---|---|---|---|---|
| R1 | `data/parsers` | `core/ingest/parsers.py` | `parse_file()` for csv, json, jsonl, pdf, md, html, txt; `load_folder()`; metadata with sha256 and source | Each format loads into `Document`s | A |
| R2 | `data/dedupe` | `core/ingest/dedupe.py` | Exact (sha256) and near-duplicate (Jaccard 0.9 or more) removal, with a report | Duplicates in a test folder are removed and reported | A |
| R3 | `data/ingest-script` | `scripts/ingest.py`, `domain/corpus.py` | Ingest the mock problem's data; `load_documents()` | `python -m scripts.ingest <folder>` writes `documents.jsonl` | PS, R1, R2 |
| R4 | `fe/meta-shell` | `frontend/src/` | Screen builds its form, labels and outcome texts from `/api/meta`; demo mode in `src/lib/api.js` | Editing a sample `ui.json` changes the screen with no React edits | A |
| R5 | `api/meta-audit` | `core/api/routes.py`, `core/audit/store.py` | `/api/meta`, `/api/ingest` upload; hash-chained runs table, `verify_chain`, masked CSV export | `/api/audit/verify` says the chain is valid | B |
| R6 | `fe/eval-review` | `frontend/src/` | Evaluation page (reads `eval_report.json`), review panel (approve, edit, reject) | Both pages work on the live backend | R5, K5 |

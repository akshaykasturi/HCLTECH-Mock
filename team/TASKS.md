# Tasks

Each person works through their own list in order. One task = one branch = one pull request.
Start a task in Claude Code with: `/start-task <branch> Task <id> from team/TASKS.md`

**A1 goes first** (about 15 minutes): it adds the shared shapes that several tasks use.
Tasks with nothing in "Needs" can start straight away. Paths are inside `backend/app/` unless they start with `backend/` or `frontend/`.

## Akshay: pipeline, search, chunking, gate

| # | Branch | Files | What to build | Done when | Needs |
|---|---|---|---|---|---|
| A1 | `core/shared-shapes` | `contracts.py` | Add `Document` and `Finding` (docs/ARCHITECTURE.md section 2); `Match.source_type` also allows `"doc"`; `Classification.candidates: list[str] = []` (conformal set); `AnalysisResult.findings: list[Finding] = []` | All existing tests pass; frontend still builds | — |
| A2 | `core/chunking` | `pipeline/chunking.py` | `chunk(doc)`: split at headings, then ~220 words with 40 overlap; ids `doc#n`; heading path in metadata; returns `Match` items with `source_type="doc"` | Tests on a sample Markdown document pass | A1 |
| A3 | `core/error-code-tokens` | `pipeline/retrieve.py` | Tokenizer keeps codes like `ERR_42`, `0x80070005`, `HTTP 429` as one token | New test passes; old search tests still pass | — |
| A4 | `core/index-docs` | `pipeline/retrieve.py` | The index also loads chunks from `backend/data/processed/documents.jsonl` when it exists | `/api/search` returns document chunks for an ingested file | A2, R3 |
| A5 | `core/route-findings` | `pipeline/orchestrator.py`, `route()` in `verify.py` | Run the checks from `checks.py` after citation checking; a `block` finding removes the step or escalates; more than one conformal candidate gives CLARIFY | Findings and the reason show in the trace | T1, S2 |


## Atheesha: LLM, safety checks, answer quality

| # | Branch | Files | What to build | Done when | Needs |
|---|---|---|---|---|---|
| T1 | `ai/numbers-check` | `pipeline/checks.py` | `check_numbers(rec, matches)`: every number in a step must appear in a cited source | Flags "500 requests" when the source says 100 | A1 |
| T2 | `ai/certainty-pii` | `pipeline/checks.py` | `check_certainty` ("definitely", "guaranteed", "confirmed" not backed by the source) and `check_pii_out` (personal data in the output) | Both return the right findings in tests | A1 |
| T3 | `ai/openai-compat` | `llm/openai_compat.py`, `llm/router.py` | One provider for any OpenAI-style API, so Groq and Ollama share code; base URL from `LLM_BASE_URL` (add it to `config.py`) | Works against the fake server in tests; Groq still works | — |
| T4 | `ai/llm-cache` | `llm/cache.py`, `llm/router.py` | Cache answers by hash of model + prompts + data version; off in tests | A repeated call returns the cached answer without calling the provider | — |
| T5 | `ai/answer-evals` | `evals/answers.py` | `citation_precision`, `groundedness`, `number_faithfulness`, `abstention` over a list of `AnalysisResult` | Hand-made results give the expected numbers | — |
| T6 | `ai/redteam` | `backend/scripts/redteam.py`, `backend/data/redteam/attacks.jsonl` | About 20 attacks: prompt injection, personal data, hazards, off-topic, typos, mixed language. Runs offline | Prints a pass rate per category | — |

## Raswanth: ML classification and training data

| # | Branch | Files | What to build | Done when | Needs |
|---|---|---|---|---|---|
| S1 | `ml/conformal` | `ml/conformal.py` | `fit_qhat()` and `predict_set()` (split conformal, alpha 0.1) | A clear ticket gives 1 candidate; an ambiguous one gives 2 or more | — |
| S2 | `ml/candidates` | `pipeline/classify.py` | Fit `qhat` on the validation set when the model is trained; fill `Classification.candidates` | Shows in `/api/analyze` results | A1, S1 |
| S3 | `ml/cost-threshold` | `ml/thresholds.py`, `backend/scripts/tune_gate.py` | `cost_threshold()`: the threshold with the lowest expected cost; `tune_gate.py` prints it next to the current choice (costs in `policy.yaml`) | Prints threshold + expected cost | — |

## Akhilesh: evaluation, maths analysis, pitch

| # | Branch | Files | What to build | Done when | Needs |
|---|---|---|---|---|---|
| K1 | `analysis/stats` | `analysis/stats.py` | `brier`, `bootstrap_ci`, `mcnemar`, `risk_coverage` | Match hand-worked examples in tests | — |
| K2 | `analysis/baselines` | `analysis/baselines.py` | Majority-class baseline (the kNN baseline already exists in `classify.py`) | Tests pass | — |
| K3 | `analysis/report-ci` | `backend/scripts/evaluate.py` | Add 95% confidence intervals, Brier score, McNemar (calibrated model vs kNN) and the majority baseline to the report | `docs/eval_report.md` shows them | K1, K2 |
| K4 | `analysis/risk-coverage` | `backend/scripts/evaluate.py` | Table: accuracy against share of tickets answered as the threshold moves | In the report | K1 |
| K5 | `analysis/answer-section` | `backend/scripts/evaluate.py` | Answer-quality section using `evals/answers.py` (extractive runs) | In the report | T5 |
| K6 | `docs/pitch-demo` | `docs/pitch/`, `docs/DEMO-SCRIPT.md` | Pitch outline and a 3-minute demo script; numbers only from `docs/eval_report.md` | Team rehearses it once | K3 |

## Roshan: data ingestion, API, database, frontend

| # | Branch | Files | What to build | Done when | Needs |
|---|---|---|---|---|---|
| R1 | `data/parsers` | `ingest/parsers.py` | `parse_file()` for csv, json, jsonl, pdf, md, html, txt; `load_folder()`; metadata with sha256 and source | Each format loads into `Document`s in tests | A1 |
| R2 | `data/dedupe` | `ingest/dedupe.py` | Exact (sha256) and near-duplicate (Jaccard 0.9 or more) removal, with a report | Duplicates in a test folder are removed and reported | A1 |
| R3 | `data/ingest-script` | `backend/scripts/ingest.py` | Load a folder, redact, dedupe, write `backend/data/processed/documents.jsonl` | One command ingests a sample folder | R1, R2 |
| R4 | `api/audit-export` | `db/`, `main.py` | Hash chain on saved analyses (`prev_hash`, `hash`), `GET /api/audit/verify`, `GET /api/export.csv` with personal data masked | Verify says the chain is valid; editing a row breaks it | — |
| R5 | `api/meta` | `ui.json`, `main.py`, `frontend/src/lib/` | `GET /api/meta` returns labels and form fields; the frontend reads them, falling back to `words.js` | Changing `ui.json` changes the screen text | — |
| R6 | `fe/findings` | `frontend/src/components/` | Show findings and conformal candidates on the result screen | Visible for a ticket that triggers them | A5 |

## When the problem statement is known

Each person adapts their own part (docs/ARCHITECTURE.md section 5) before building new features:
Akshay the models and policy, Raswanth the categories and training data, Roshan the documents and the screen labels, Atheesha the prompt, schema and attack cases, Akhilesh the test sets and the report.

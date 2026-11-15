# Architecture

What the app is, where each part lives and who leads it (who to ask, not who is allowed). The code is the working IT ticket assistant; we keep its layout.
If code and this file disagree, fix one of them.

## 1. The pipeline: `backend/app/pipeline/orchestrator.py`, `analyse(ticket, llm) -> AnalysisResult`

```
ticket -> 1 redact -> 2 classify -> 3 retrieve -> 4 gate -> 5 generate -> 6 verify + route -> saved + shown
                                                     |
                                                     +-> stops here (ESCALATE or CLARIFY) with no LLM call
```

| Step | What it does | File | Lead |
|---|---|---|---|
| 1 redact | Masks emails, phone numbers, IPs and secrets before anything else sees the text | `pipeline/redact.py` | Atheesha |
| 2 classify | Category, subcategory, priority, calibrated confidence | `pipeline/classify.py` | Raswanth |
| 3 retrieve | Hybrid search: BM25 keywords + embeddings, fused with RRF. Strength = cosine similarity of the best match | `pipeline/retrieve.py`, `pipeline/embed.py` | Akshay |
| 4 gate | Safety keywords and prompt attacks (ESCALATE), vague text (CLARIFY), weak evidence (ESCALATE), before any LLM call | `pipeline/gate.py` | Akshay (the safety and injection lists in `policy.yaml`: Atheesha) |
| 5 generate | The LLM writes JSON steps with citations from the retrieved matches; extractive fallback with no LLM | `pipeline/generate.py`, `llm/` | Atheesha |
| 6 verify + route | Drops citations not found word for word; picks the outcome; confidence = min(signals) | `pipeline/verify.py` | Atheesha (verify), Akshay (route rules) |
| save + API | Analyses and feedback saved; HTTP endpoints | `main.py`, `db/` | Roshan |
| screen | React app | `frontend/` | Roshan |
| evaluate | Classification, search and routing metrics on the test sets | `scripts/evaluate.py` | Akhilesh |

Outcomes: `RECOMMEND` (fix shown), `CLARIFY` (ask for more detail), `ESCALATE` (hand to a person).
Signals (0 to 1): `classifier`, `retrieval`, `grounding`. Confidence = the smallest.
Rule: deterministic code decides; the LLM only writes words; code checks every LLM output.

## 2. Shared data shapes: `backend/app/contracts.py` (lead Akshay)

Existing models (read the file for fields): `TicketIn`, `SearchFilters`, `SearchRequest`, `Classification`, `Match`, `Citation`, `Recommendation`, `AuditEvent`, `AnalysisResult`, `FeedbackIn`, `FeedbackOut`, `AnalysisSummary`, `AnalysisRecord`, `Stats`, `ErrorInfo`, `Envelope`.
The frontend and the database depend on them: say so in the pull request when you change one.

To be added in task A1 (`team/TASKS.md`), so new modules share them:

```python
class Document(BaseModel):     # one loaded file or record, before chunking
    id: str
    title: str
    text: str
    source: str                # file path or URL
    metadata: dict[str, Any] = {}   # format, sha256, loaded_at, licence, url, version

class Finding(BaseModel):      # the result of one safety or quality check
    code: str                  # e.g. "NUMBER_NOT_IN_SOURCE"
    severity: Literal["info", "warn", "block"]
    message: str

# Match.source_type also gains "doc" (chunks of loaded documents)
```

## 3. File map

Paths are inside `backend/app/` unless they start with `backend/`, `frontend/`, `docs/` or `team/`.

### Existing files

| File | Lead | What it holds |
|---|---|---|
| `contracts.py` | Akshay (shared) | All shared models |
| `config.py` | Akshay (shared) | `get_settings()`, `get_policy()`; settings from environment variables |
| `policy.yaml` | Akshay; sections `safety_keywords` and `injection_patterns`: Atheesha | Every threshold and rule |
| `pipeline/orchestrator.py` | Akshay | `analyse()`: runs the 6 steps, writes the trace |
| `pipeline/retrieve.py` | Akshay | `Index.search(query, top_k, filters)`, `Index.rank(..., mode="bm25"/"dense"/"hybrid")`, `rrf()`, `tokenize()` |
| `pipeline/embed.py` | Akshay | `FastEmbedder` (bge-small), `HashEmbedder` (tests), `get_embedder()` |
| `pipeline/gate.py` | Akshay | `check(text, strength, policy)`, `stop_outcome()`, `safety_hit()`, `injection_hit()` |
| `pipeline/classify.py` | Raswanth | TF-IDF + calibrated logistic regression; `classify(text)`, `load_or_train()`, `knn_vote()` baseline |
| `pipeline/redact.py` | Atheesha | `redact(text) -> (text, counts)` |
| `pipeline/generate.py` | Atheesha | `SYSTEM` prompt, `SCHEMA`, `generate(text, matches, llm)`, `extractive()` |
| `pipeline/verify.py` | Atheesha (`verify_citations`); Akshay (`route`) | Citation check; outcome rules |
| `llm/` (`base.py`, `fake.py`, `gemini.py`, `groq.py`, `router.py`) | Atheesha | Providers, `ChainLLM` with circuit breaker, `run_llm()`, `build_llm()` |
| `main.py` | Roshan | FastAPI app and all endpoints |
| `db/` (`models.py`, `repository.py`, `session.py`) | Roshan | Analyses and feedback tables; SQLite locally, Postgres in production; database-down handling |
| `warmup.py` | Roshan | Builds the index and classifier at startup |
| `backend/scripts/build_index.py` | Akshay | Pre-builds search vectors and the classifier |
| `backend/scripts/tune_gate.py` | Raswanth | Picks the gate threshold on the validation set |
| `backend/scripts/generate_data.py`, `scenarios.py` | Raswanth | Synthetic training data and scenarios |
| `backend/scripts/evaluate.py` | Akhilesh | Writes `docs/eval_report.md` |
| `backend/scripts/check_llm.py` | Atheesha | Checks each LLM provider responds |
| `backend/data/historical_tickets.csv`, `kb_articles.json`, `DATA_CARD.md` | Raswanth | Training and search data |
| `backend/data/test/`, `backend/data/validation/` | Akhilesh | Test sets (never tuned on) and the validation set (tuning only) |
| `backend/Dockerfile`, `.github/workflows/ci.yml` | Akshay | Deploy and CI |
| `frontend/` | Roshan | React + Vite + Tailwind; API calls in `src/lib/api.js`; labels in `src/lib/words.js` |

### New files (agreed paths; create them here)

| File | Lead | Functions |
|---|---|---|
| `pipeline/chunking.py` | Akshay | `chunk(doc: Document, max_words: int = 220, overlap: int = 40) -> list[Match]` |
| `ingest/parsers.py` | Roshan | `parse_file(path: Path) -> list[Document]`; `load_folder(folder: Path) -> list[Document]` |
| `ingest/dedupe.py` | Roshan | `dedupe(docs: list[Document]) -> tuple[list[Document], list[dict]]` |
| `backend/scripts/ingest.py` | Roshan | Loads a folder, writes `backend/data/processed/documents.jsonl` |
| `ml/conformal.py` | Raswanth | `fit_qhat(cal_probs, cal_labels, alpha=0.1) -> float`; `predict_set(probs: dict[str, float], qhat: float) -> list[str]` |
| `ml/thresholds.py` | Raswanth | `cost_threshold(scores, correct, cost_wrong_pass, cost_needless_escalation) -> tuple[float, float]` |
| `analysis/stats.py` | Akhilesh | `brier()`, `bootstrap_ci(values, n=2000, alpha=0.05, seed=0) -> (point, low, high)`, `mcnemar(a_correct, b_correct) -> dict`, `risk_coverage(confidence, correct) -> list[dict]` |
| `analysis/baselines.py` | Akhilesh | `majority_baseline()`, `keyword_baseline()` |
| `pipeline/checks.py` | Atheesha | `check_numbers(rec, matches)`, `check_certainty(rec, matches)`, `check_pii_out(rec)`, each `-> list[Finding]` |
| `llm/openai_compat.py` | Atheesha | One provider for any OpenAI-style API (Groq, or Ollama through `LLM_BASE_URL`) |
| `llm/cache.py` | Atheesha | `get(key) -> dict | None`, `put(key, value) -> None` |
| `evals/answers.py` | Atheesha | `citation_precision()`, `groundedness()`, `number_faithfulness()`, `abstention()` |
| `backend/scripts/redteam.py`, `backend/data/redteam/` | Atheesha | Attack cases and pass rate per category |
| `ui.json` | Roshan | Labels, form fields and outcome texts for `GET /api/meta` |

New folders (`ingest/`, `ml/`, `analysis/`, `evals/`) need an empty `__init__.py`.

## 4. API (lead Roshan)

Every response: `{"ok": bool, "request_id": str, "data": ..., "error": {"code": str, "message": str} | null}`.

Existing: `GET /health` · `POST /api/analyze` · `GET /api/analyses` · `GET /api/analyses/{id}` · `POST /api/analyses/{id}/feedback` · `GET /api/stats` · `POST /api/search`
Planned: `GET /api/meta` · `GET /api/export.csv` (personal data masked) · `GET /api/audit/verify` · `POST /api/ingest`

The frontend depends on paths and response shapes: change them only together with the frontend.

## 5. What changes for a new problem statement

| What | Where | Lead |
|---|---|---|
| Input and output models | `contracts.py` (`TicketIn`, `Classification`, `Recommendation`) | Akshay |
| Categories and training data | `backend/data/`, `scripts/generate_data.py`, `classify.py` | Raswanth |
| Documents to search | Files into `backend/data/raw/` → ingest → chunking → index | Roshan, then Akshay |
| Prompt and output schema | `pipeline/generate.py` (`SYSTEM`, `SCHEMA`) | Atheesha |
| Rules and thresholds | `policy.yaml` | Akshay (safety lists: Atheesha) |
| Screen labels and form | `frontend/src/components/TicketForm.jsx`, `src/lib/words.js` (later `ui.json`) | Roshan |
| Test and validation sets; report | `backend/data/test/`, `backend/data/validation/`, `scripts/evaluate.py` | Akhilesh |
| Attack cases | `backend/data/redteam/` | Atheesha |

## 6. Data and evaluation rules

- Splits: training data, validation (tuning only), test (never used to choose anything).
- Live-LLM runs and extractive (no-LLM) runs are reported separately.
- Numbers in the README, pitch or demo come from `docs/eval_report.md`, never typed by hand.
- Each metric shows its value, sample size and the baseline next to it, with a 95% confidence interval where `analysis/stats.py` provides one.

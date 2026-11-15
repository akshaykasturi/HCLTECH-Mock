# Architecture

The single source of truth for what we build. If code and this file disagree, this file wins until Akshay changes it in a pull request.

## 1. The pipeline

```
input -> guard_in -> classify -> retrieve -> gate -> generate -> guard_out -> route -> audit
                                                                                  |
                                              review by a human  <----------------+
                                              evaluate offline (scripts/evaluate.py)
```

| Step | What it does | Owner | Lives in |
|---|---|---|---|
| guard_in | Hide personal data and secrets; flag prompt attacks, hazards, vague input | Atheesha | `core/guardrails/` |
| classify | Category, calibrated probability, conformal set | Raswanth | `core/ml/`, `domain/steps.py` |
| retrieve | Hybrid search (keyword BM25 + embeddings, fused with RRF) over approved chunks | Akshay | `core/retrieval/` |
| gate | Weak evidence stops the run before any LLM call | Akshay | `core/gate.py` |
| generate | The LLM writes strict JSON from the evidence only | Atheesha | `core/llm/`, `domain/prompts.py` |
| guard_out | Check citations, numbers, certainty words, IDs, personal data in the output | Atheesha | `core/guardrails/`, `domain/checks.py` |
| route | Final outcome; confidence = min(signals) | Akshay | `core/pipeline.py` |
| audit | Save the run in a hash-chained table | Roshan | `core/audit/` |
| api + screen | Endpoints; screen built from `ui.json` | Roshan | `core/api/`, `frontend/` |
| evaluate | ML, search and answer metrics with confidence intervals and baselines | Akhilesh, with metric functions from each owner | `core/analysis/`, `scripts/evaluate.py` |

Outcomes: `RECOMMEND` (answer shown), `CLARIFY` (ask the user a question), `ESCALATE` (send to a human), `BLOCKED` (policy forbids it).

Signals (each 0 to 1): `classifier_prob` (Raswanth), `evidence_strength` (Akshay), `groundedness` (Atheesha). A conformal set with more than one category means CLARIFY. Confidence = the smallest signal.

## 2. Contracts: `backend/app/core/contracts.py` (owner Akshay)

Everyone imports these. Nobody redefines them.

```python
class Document(BaseModel):      # one loaded file or record, before chunking
    id: str
    title: str
    text: str
    source: str                 # file path or URL
    metadata: dict = {}         # format, sha256, loaded_at, licence, version, date, access

class Evidence(BaseModel):      # anything we can cite: a chunk, a past record, a log line
    id: str                     # chunk id: f"{document_id}#{n}"
    source_type: str            # "doc", "ticket", "log", ...
    title: str
    text: str
    score: float = 0.0          # evidence strength 0..1, set by search()
    metadata: dict = {}         # heading path, page, section, url, licence, status

class Citation(BaseModel):
    evidence_id: str
    excerpt: str                # must appear word for word in that evidence
    reason: str
    also_in: list[str] = []

class Finding(BaseModel):
    code: str                   # e.g. "NUMBER_NOT_IN_SOURCE"
    severity: Literal["info", "warn", "block"]
    message: str

class Signal(BaseModel):
    name: str
    value: float                # 0..1

class AuditEvent(BaseModel):
    step: str
    ms: float = 0.0
    detail: dict = {}

Outcome = Literal["RECOMMEND", "CLARIFY", "ESCALATE", "BLOCKED"]

class RunContext(BaseModel):    # passed through every step; steps read and write it
    run_id: str
    domain: str
    input: dict = {}
    input_redacted: dict = {}
    query: str = ""
    category: str | None = None
    category_probs: dict[str, float] = {}
    category_set: list[str] = []
    evidence: list[Evidence] = []
    allowed_ids: list[str] = []
    output: dict | None = None  # the domain OutputModel as a dict
    findings: list[Finding] = []
    signals: list[Signal] = []
    reasons: list[str] = []
    outcome: Outcome | None = None
    generator: str | None = None  # "gemini", "groq", "ollama", "extractive"
    stop: bool = False
    trace: list[AuditEvent] = []

class RunResult(BaseModel):
    run_id: str
    domain: str
    input_redacted: dict
    outcome: Outcome
    reasons: list[str]
    confidence: float
    signals: list[Signal]
    evidence: list[Evidence]
    output: dict | None
    findings: list[Finding]
    generator: str | None
    trace: list[AuditEvent]

@dataclass
class DomainPack:
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]                         # the strict JSON the LLM must return
    load_documents: Callable[[], list[Document]]
    build_query: Callable[[BaseModel], str]
    build_prompt: Callable[[RunContext], tuple[str, str]]  # (system, user)
    steps: list[Callable[[RunContext], None]]
    policy_path: Path
    ui_path: Path
```

Every step has the shape `def step(ctx: RunContext) -> None`. It may set `ctx.stop`, `ctx.outcome` and `ctx.reasons`.
Every check has the shape `def check(ctx: RunContext) -> list[Finding]`.

## 3. Module map

Signatures are fixed. "New" means a stub is created first and the owner implements it. "Port" means existing working code is moved here.

| File (under `backend/app/` or `backend/`) | Owner | Status | Signatures |
|---|---|---|---|
| `core/ingest/parsers.py` | Roshan | new | `parse_file(path: Path) -> list[Document]`; `load_folder(folder: Path) -> list[Document]` |
| `core/ingest/dedupe.py` | Roshan | new | `dedupe(docs: list[Document]) -> tuple[list[Document], list[dict]]` (kept, removed-report) |
| `core/chunking.py` | Akshay | new | `chunk(doc: Document, max_words: int = 220, overlap: int = 40) -> list[Evidence]` |
| `core/retrieval/index.py` | Akshay | port | `build_index(evidence: list[Evidence]) -> None`; `search(query: str, k: int = 5, filters: dict \| None = None, mode: str = "hybrid") -> list[Evidence]` |
| `core/retrieval/metrics.py` | Akshay | new | `recall_at_k(ranked: list[str], gold: set[str], k: int) -> float`; `mrr(ranked: list[str], gold: set[str]) -> float`; `ndcg_at_k(ranked: list[str], gold: set[str], k: int) -> float` |
| `core/gate.py` | Akshay | port | `gate(ctx: RunContext) -> None` |
| `core/pipeline.py` | Akshay | new | `run(domain: DomainPack, raw_input: dict) -> RunResult` |
| `core/ml/classifier.py` | Raswanth | port | `train(texts: list[str], labels: list[str]) -> None`; `predict(text: str) -> tuple[str, float, dict[str, float]]` |
| `core/ml/conformal.py` | Raswanth | new | `fit_qhat(cal_probs: np.ndarray, cal_labels: np.ndarray, alpha: float = 0.1) -> float`; `predict_set(probs: dict[str, float], qhat: float) -> list[str]` |
| `core/ml/thresholds.py` | Raswanth | new | `cost_threshold(scores: np.ndarray, correct: np.ndarray, cost_wrong_pass: float, cost_needless_escalation: float) -> tuple[float, float]` (threshold, expected cost) |
| `core/analysis/stats.py` | Akhilesh | new | `calibration(y_true: np.ndarray, p: np.ndarray, bins: int = 10) -> dict`; `bootstrap_ci(values: np.ndarray, n: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]`; `mcnemar(a_correct: np.ndarray, b_correct: np.ndarray) -> dict`; `risk_coverage(confidence: np.ndarray, correct: np.ndarray) -> list[dict]` |
| `core/analysis/baselines.py` | Akhilesh | new | `majority_baseline(train_labels: list[str], n: int) -> list[str]`; `keyword_baseline(texts: list[str], keywords: dict[str, list[str]]) -> list[str]` |
| `core/llm/gateway.py` | Atheesha | new | `generate(schema: type[BaseModel], system: str, user: str, allowed_ids: list[str]) -> tuple[dict \| None, str, list[str]]` (output, provider, errors) |
| `core/llm/providers/` | Atheesha | port | `gemini.py`, `openai_compat.py` (Groq or Ollama through `LLM_BASE_URL`), `fake.py` |
| `core/llm/cache.py` | Atheesha | new | `get(key: str) -> dict \| None`; `put(key: str, value: dict) -> None` |
| `core/guardrails/redact.py` | Atheesha | port | `redact(text: str) -> tuple[str, list[Finding]]` |
| `core/guardrails/input_checks.py` | Atheesha | port | `check_injection(ctx) -> list[Finding]`; `check_hazard(ctx) -> list[Finding]`; `check_vague(ctx) -> list[Finding]` |
| `core/guardrails/citations.py` | Atheesha | port | `check_citations(ctx) -> list[Finding]` (word-for-word excerpt, allowed IDs, merge duplicate quotes) |
| `core/guardrails/numbers.py` | Atheesha | new | `check_numbers(ctx) -> list[Finding]` |
| `core/guardrails/certainty.py` | Atheesha | new | `check_certainty(ctx) -> list[Finding]` |
| `core/guardrails/pii_out.py` | Atheesha | new | `check_pii_out(ctx) -> list[Finding]` |
| `core/evals/rag.py` | Atheesha | new | `citation_precision(results: list[RunResult]) -> float`; `groundedness(results: list[RunResult]) -> float`; `number_faithfulness(results: list[RunResult]) -> float`; `abstention(results: list[RunResult], expected: list[str]) -> dict` |
| `core/audit/store.py` | Roshan | port | `save_run(result: RunResult) -> str`; `get_run(run_id: str) -> RunResult \| None`; `list_runs(limit: int = 50) -> list[dict]`; `verify_chain() -> dict`; `export_csv() -> str` |
| `core/api/routes.py` | Roshan | port | FastAPI router with the endpoints in section 4 |
| `scripts/ingest.py` | Roshan | new | `python -m scripts.ingest <folder>` writes `data/processed/documents.jsonl` |
| `scripts/tune_gate.py` | Raswanth | port | Prints the best gate threshold from the validation set; Akshay copies it into `policy.yaml` |
| `scripts/redteam.py` | Atheesha | new | Runs `data/redteam/*.jsonl`, prints the pass rate per category |
| `scripts/evaluate.py` | Akhilesh | new | Writes `data/eval_report.json` and `docs/eval_report.md` |

## 4. API (owner Roshan)

Every response: `{"ok": bool, "request_id": str, "data": ..., "error": {"code": str, "message": str} | null}`.

`GET /health` · `GET /api/meta` (domain name + `ui.json`) · `POST /api/run` · `GET /api/runs` · `GET /api/runs/{id}` · `POST /api/runs/{id}/feedback` · `POST /api/runs/{id}/review` · `GET /api/stats` · `GET /api/export.csv` (personal data masked) · `GET /api/audit/verify` · `POST /api/search` · `POST /api/ingest` (file upload)

Paths and response shapes are fixed: the frontend depends on them.

## 5. Domain pack: `backend/app/domain/` (written for each problem statement)

| File | Owner | What goes in it |
|---|---|---|
| `__init__.py` | Akshay | `DOMAIN = DomainPack(...)`, the only thing core imports |
| `contracts.py` | Akshay | `InputModel`, `OutputModel` (the LLM's JSON), the category list |
| `corpus.py` | Roshan | `load_documents() -> list[Document]` |
| `steps.py` | Raswanth | Domain steps, such as classify wiring and domain rules |
| `prompts.py` | Atheesha | `build_prompt(ctx) -> (system, user)` |
| `checks.py` | Atheesha | Domain output checks returning `list[Finding]` |
| `policy.yaml` | Akshay (others propose values in their pull request text) | Thresholds, keywords, costs |
| `ui.json` | Roshan | Form fields, labels, outcome texts, example inputs |

Reference pack: `backend/app/domains/tickets/` (IT tickets, working). Copy it, then adapt.

## 6. Data and evaluation rules

- Splits: train, validation (tuning only), test (never used for a decision). Each split's source and size go in `data/eval/README.md`.
- Live-LLM runs and extractive (no-LLM) runs are reported separately.
- Every number in the README, pitch or demo comes from `data/eval_report.json`. Never type a number by hand.
- Every metric shows its value, 95% confidence interval, sample size and the baseline next to it.

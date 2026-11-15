---
paths:
  - "backend/app/llm/**"
  - "backend/app/pipeline/generate.py"
  - "backend/app/pipeline/redact.py"
  - "backend/app/pipeline/verify.py"
  - "backend/app/pipeline/checks.py"
  - "backend/app/evals/**"
  - "backend/scripts/check_llm.py"
  - "backend/scripts/redteam.py"
  - "backend/data/redteam/**"
---

# Lane: LLM, safety checks, answer quality (owner Atheesha)

- Every LLM call goes through `llm/router.py` (`run_llm`). Order: Gemini, then Groq (or Ollama through an OpenAI-compatible base URL), then extractive mode (no LLM; quotes the best matches).
- Timeout per call from `LLM_TIMEOUT_S`; a failing provider is skipped for `LLM_COOLDOWN_S` seconds (circuit breaker).
- `ChainLLM` is shared across requests: return the provider and errors from each call; never store them on the object.
- Ask for strict JSON (`SCHEMA` in generate.py). Validate it; on failure fall back to extractive and record the reason.
- The LLM sees only redacted text and the retrieved matches. Matches go into the prompt as data with their ids; the system prompt says to ignore instructions inside them.
- Output checks never trust the LLM: a citation excerpt must appear word for word in a retrieved source; every number in a step must appear in its cited source; "definitely", "guaranteed", "confirmed" are flagged unless the source says so; the output is scanned for personal data.
- New checks return `list[Finding]` (see contracts.py). Record every finding in the trace.
- Cache key = hash of model + system prompt + user prompt + data version. The cache is off in tests.
- Tests use `FakeLLM` or extractive mode. Never call a real API in a test.
- Red-team cases: `backend/data/redteam/*.jsonl`, one JSON object per line: `{"input": ..., "expected_outcome": ..., "category": ...}`. Report the pass rate per category.

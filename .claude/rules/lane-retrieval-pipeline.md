---
paths:
  - "backend/app/core/retrieval/**"
  - "backend/app/core/chunking.py"
  - "backend/app/core/gate.py"
  - "backend/app/core/pipeline.py"
  - "backend/app/core/contracts.py"
  - "backend/app/domain/__init__.py"
  - "backend/app/domain/contracts.py"
  - "backend/app/domain/policy.yaml"
---

# Lane: search, chunking, gate, pipeline (owner Akshay)

- `search()` never calls an LLM. Hybrid search = BM25 (`rank-bm25`) + embeddings (fastembed `BAAI/bge-small-en-v1.5`, numpy cosine), fused with reciprocal rank fusion (k = 60).
- Tests use `HashEmbedder`, never the real embedding model.
- The approved-only filter (`policy.yaml` retrieval statuses) is applied before ranking, never after.
- `Evidence.score` is the evidence strength from 0 to 1 that the gate uses. The docstring of `search()` says how it is computed.
- Chunking splits on headings first, then into about 220 words with a 40-word overlap. Chunk id = `f"{doc.id}#{n}"`. Keep the heading path, page and section in metadata so citations can show them.
- The tokenizer strips placeholders like `[EMAIL]` and keeps error codes (`ERR_42`, `0x80070005`, `HTTP 429`) as one token.
- Gate thresholds come from `policy.yaml` and are tuned on the validation set by `scripts/tune_gate.py`. Never hardcode them.
- `pipeline.run` times each step, appends an `AuditEvent`, stops when a step sets `ctx.stop`, and sets confidence = min(signals).
- A change to `contracts.py` affects all five people: announce it in the group and record it in `docs/DECISIONS.md`.

---
paths:
  - "backend/app/pipeline/orchestrator.py"
  - "backend/app/pipeline/retrieve.py"
  - "backend/app/pipeline/embed.py"
  - "backend/app/pipeline/gate.py"
  - "backend/app/pipeline/chunking.py"
  - "backend/app/contracts.py"
  - "backend/app/policy.yaml"
  - "backend/scripts/build_index.py"
---

# Lane: pipeline, search, chunking, gate

- Search never calls an LLM. Hybrid = BM25 (`rank-bm25`) + embeddings (fastembed `BAAI/bge-small-en-v1.5`, numpy cosine), fused with RRF (`retrieval.rrf_k` in policy.yaml).
- Tests use `HashEmbedder`; `tests/conftest.py` already sets this.
- Only approved knowledge is searchable (`retrieval.kb_statuses_allowed`); filter before ranking, never after.
- Retrieval strength = cosine similarity of the best match. The gate threshold is per embedding model in `gate.min_retrieval_strength`, tuned by `scripts/tune_gate.py` on the validation set only.
- Chunking: split on headings first, then about 220 words with a 40-word overlap. Chunk id `f"{doc.id}#{n}"`; keep heading path, page and section in metadata so citations can show them.
- The tokenizer strips redaction placeholders like `[EMAIL]` and should keep error codes (`ERR_42`, `0x80070005`) as one token.
- `analyse()` appends an `AuditEvent` for every step and stops early when the gate says so.
- Changing `contracts.py` affects everyone: say so in the pull request and record it in `docs/DECISIONS.md`.

---
paths:
  - "backend/app/core/ingest/**"
  - "backend/app/core/api/**"
  - "backend/app/core/audit/**"
  - "backend/app/domain/corpus.py"
  - "backend/app/domain/ui.json"
  - "backend/scripts/ingest.py"
  - "frontend/**"
---

# Lane: data ingestion, API, database, frontend (owner Roshan)

Ingestion
- `parse_file` handles .csv, .json, .jsonl, .pdf (pypdf), .md, .html (beautifulsoup4), .txt. An unknown type raises a clear error.
- Every `Document` gets metadata: format, sha256 of the text, loaded_at, licence and source URL when known.
- Redact on ingest by calling `app.core.guardrails.redact.redact()`. Never copy its code.
- `dedupe`: exact duplicates by sha256; near-duplicates by word-shingle Jaccard similarity of 0.9 or more. Return a report of what was removed.

API
- Every response uses the envelope in docs/ARCHITECTURE.md section 4. Paths and shapes are fixed.
- Database unreachable: return 503 `DATABASE_UNAVAILABLE`, never crash.
- The audit table is append-only: each row stores `prev_hash` and `hash = sha256(prev_hash + row JSON)`. `verify_chain` walks the chain.
- CSV export masks personal data.

Frontend
- React 18 + Vite + Tailwind. Labels, form fields and outcome texts come from `GET /api/meta`. No problem-specific words hardcoded in components.
- API calls only in `src/lib/api.js`. Demo mode returns saved responses when the backend is down.
- Every call shows a loading state and an error state.

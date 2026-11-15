---
paths:
  - "backend/app/main.py"
  - "backend/app/db/**"
  - "backend/app/warmup.py"
  - "backend/app/ingest/**"
  - "backend/app/ui.json"
  - "backend/scripts/ingest.py"
  - "backend/data/raw/**"
  - "frontend/**"
---

# Lane: data ingestion, API, database, frontend

Ingestion
- `parse_file` handles .csv, .json, .jsonl, .pdf (pypdf), .md, .html (beautifulsoup4), .txt. An unknown type raises a clear error.
- Every `Document` gets metadata: format, sha256 of the text, loaded_at, and source URL and licence when known.
- Redact on ingest by calling `app.pipeline.redact.redact()`; don't copy its code.
- Dedupe: exact by sha256, near-duplicates by word-shingle Jaccard similarity of 0.9 or more; report what was removed.

API and database
- Every response uses the envelope in docs/ARCHITECTURE.md section 4.
- Database unreachable: return 503 `DATABASE_UNAVAILABLE`, never crash (existing behaviour; keep it).
- Saved records are append-only. For a hash chain: each row stores `prev_hash` and `hash = sha256(prev_hash + row JSON)`; a verify endpoint walks the chain.
- CSV export masks personal data.

Frontend
- React 18 + Vite + Tailwind. API calls only in `src/lib/api.js`; labels in `src/lib/words.js` (later from `GET /api/meta`).
- Every call shows a loading state and an error state. Keep the existing look; don't restyle what you weren't asked to.
- `npm run lint` and `npm run build` must pass (CI runs both).

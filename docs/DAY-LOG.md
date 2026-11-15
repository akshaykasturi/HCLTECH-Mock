# Day log

What existed before the event and what we built during it. Judges may ask. Owner: Akshay, from each pull request's text.

## Before the event (the chassis)

- 2026-11-16: imported the working IT ticket assistant from the earlier `ticket-assistant` project (backend, frontend, data, tests, CI). Branch `chore/import-and-fix`.
- Backend (FastAPI): pipeline redact -> classify -> retrieve -> gate -> generate -> verify/route in `backend/app/pipeline/`; outcomes RECOMMEND / CLARIFY / ESCALATE.
- Search is hybrid (BM25 + fastembed embeddings, hash embedder offline); classifier is scikit-learn; LLM is Gemini with Groq fallback behind `backend/app/llm/`, plus an offline fake; SQLite locally or Postgres via `DATABASE_URL` for saved analyses and feedback.
- Frontend: React + Vite + Tailwind in `frontend/`. Data: historical tickets, KB articles, validation and test sets in `backend/data/`.
- Checks on import: 139 backend tests pass offline; frontend builds and lints; GitHub Actions CI runs both. Still to do: port this code into the `core/` and `domain/` layout from docs/ARCHITECTURE.md.

## During the event

| Time | Who | What was built |
|---|---|---|

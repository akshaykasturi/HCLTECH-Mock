# UC4 Incident Diagnostics: frontend

React app for the UC4 API failure diagnosis assistant. It shows the cases, runs the team's real diagnosis pipeline through the FastAPI backend, and lets a reviewer confirm, reject or annotate a diagnosis.

The browser never diagnoses anything itself. Every outcome, cause, piece of evidence and report on screen comes from the backend. Causes are shown as **likely / probable / unsupported**, never as confirmed: only a reviewer confirms a cause.

> **Reports are written by a template today.** The backend's `generator` field is `"template"`, and the UI says "Written by template". When the team connects an LLM writer, the UI will show whatever `generator` value the backend sends (e.g. `gemini`, `groq`).

## Requirements

- Node.js **20.19 or newer** (CI uses Node 20; developed on Node 26).
- The FastAPI backend running on `http://127.0.0.1:8000` (see `backend/`).

## Setup and scripts

```powershell
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173 (the port the backend's CORS allows)
npm run test -- --run  # all unit and UI tests, once (without --run, Vitest watches)
npm run lint           # ESLint, zero warnings allowed
npm run build          # type-check + production build into dist/
```

Start the backend first (from `backend/`):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Backend URL

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Empty: the app calls same-origin paths, and the Vite dev server proxies `/api` and `/health` to the backend. Set it for a deployed build. |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the dev proxy sends requests. |

Copy `.env.example` to `.env.local` (git-ignored) to change them. Every `VITE_*` value is visible in the browser, so never put a secret there. The page for system status is `/system-health`, not `/health`, so it never collides with the backend's `/health` endpoint behind the proxy.

## Screens

| Screen | Route | Backend calls |
|---|---|---|
| Dashboard | `/` | `GET /api/cases`, `GET /health` |
| Case Explorer | `/cases` | `GET /api/cases` (search, route/split filters, sorting, pagination, preview) |
| Diagnosis workspace | `/diagnosis`, `/diagnosis/:caseId` | `POST /api/diagnose` `{ "case_id": "UC4-0001" }` |
| Saved diagnosis | `/diagnoses/:diagnosisId` | `GET /api/diagnoses/{id}` (never re-runs the pipeline) |
| Evidence Explorer | `/evidence?d=<id>&focus=<evidence id>` | uses the diagnosis's `evidence` and the `evidence_ids` of each ranked cause's signals |
| Human Review | `/review?d=<id>` | `POST` and `GET /api/diagnoses/{id}/feedback` |
| Audit History | `/audit` | `GET /api/audit/verify`, `GET /api/diagnoses/{id}` |
| System Health | `/system-health` | `GET /health`, `GET /health/ready` |

What the diagnosis view shows (the final `models.Diagnosis`):
- **Outcome:** `RECOMMEND` or `CLARIFY`. Escalation is the `escalate` flag, shown as an *Escalate* badge, never as a third outcome.
- **Ranked causes:** `ranked`, sorted by `rank`. Each shows its status, its confidence, any near tie, its first check, and its supporting and contradicting signals, with links to the evidence they cite.
- **Confidence display rule:** above 0.99 shows as `> 0.99`, below 0.01 as `< 0.01`, anything else to two decimals. The display never changes the stored value.
- **Close call:** shown from `alternatives` and `tell_apart`.
- **Report:** summary, cause explanations with quoted citations, verification steps, escalation team and reason, missing information. A `null` report is shown as "No report".
- **Report checks:** `groundedness` and `report_findings`.
- **"How this was decided":** the `trace` steps.
- **Missing evidence:** an evidence ID that is cited but not in the evidence list is shown with a warning, never invented.

Feedback sends `cause_id` only when a cause is chosen, and its value is always a `ranked[].cause` name, never a rank. Leaving it out means feedback on the whole diagnosis. An annotation needs a note.

## Tests

- `npm run test -- --run` runs 144 tests: the API client, formatting and validation helpers, and UI tests for every screen. The UI tests use a controlled `fetch` mock that answers in the backend's `{ok, data, error}` envelope. They cover errors 404, 422, 500, 502, 503, 504, network failures and timeouts, plus accessibility and security checks.
- **Live integration (optional):** these tests render the real app against the real backend through the dev proxy. Start the backend and `npm run dev`, then:

  ```powershell
  $env:VITE_LIVE_API_URL = "http://127.0.0.1:5173"
  npx vitest --run src/live --pool=forks --poolOptions.forks.singleFork=true
  Remove-Item Env:VITE_LIVE_API_URL
  ```

  They check real cases: `UC4-0001` (RECOMMEND), `UC4-0019` (escalate), `UC4-0085` (CLARIFY), `UC4-0006` (close call). They also submit feedback, read the history, and verify the audit chain. Note that they write feedback into the backend's audit database, so point `UC4_AUDIT_DB` at a scratch file first.

## Security and privacy

- No HTML from the backend is ever rendered. All text goes through React text nodes, and lint forbids `dangerouslySetInnerHTML`.
- Nothing is written to `localStorage`, `sessionStorage` or cookies. Diagnoses opened in a tab are kept in memory only.
- Evaluation labels (`expected_cause` and the like) are never sent by the backend and never displayed. The tests check both.
- Evidence text is already masked by the backend. The UI shows it as received.

## Known limitations

- **No audit timeline:** the backend has no endpoint that lists audit events, so the Audit History timeline shows "Integration pending". You can verify the chain and look up one diagnosis by ID instead.
- **"Diagnoses in this session"** lists only diagnoses opened in the current browser tab. It is not a history from the server.
- **Fonts:** Inter and JetBrains Mono load from Google Fonts. Offline, the app falls back to system fonts.

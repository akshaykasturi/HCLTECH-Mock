# Team rules for every Claude Code session in this repo

Five people build one app, each with their own Claude Code. These rules keep all of us building the same thing the same way.
The full design is imported below from docs/ARCHITECTURE.md. Read it before writing code.

@docs/ARCHITECTURE.md

## Who you are working for

`CLAUDE.local.md` (in the repo root, not committed) says which person you are helping and which folders they own.
If it is missing, stop and ask the human to copy theirs from `team/personal/<name>/`.

## The one design rule

Deterministic code decides. The LLM only writes words. Code checks every LLM output before anyone sees it.
Never fake AI results with hardcoded outputs.

## Folders: edit only your human's folders

| Person | Lane | Folders |
|---|---|---|
| Akshay | Contracts, pipeline, search, chunking, gate; integrator | `core/contracts.py`, `core/pipeline.py`, `core/chunking.py`, `core/gate.py`, `core/retrieval/`, `domain/__init__.py`, `domain/contracts.py`, `domain/policy.yaml`, `domains/` |
| Atheesha | LLM gateway, safety checks, answer evaluation | `core/llm/`, `core/guardrails/`, `core/evals/`, `domain/prompts.py`, `domain/checks.py`, `scripts/redteam.py`, `data/redteam/` |
| Raswanth | ML classification | `core/ml/`, `domain/steps.py`, `scripts/tune_gate.py`, `scripts/train.py` |
| Akhilesh | Maths analysis, evaluation report, pitch | `core/analysis/`, `scripts/evaluate.py`, `data/eval/`, `docs/pitch/`, `docs/DEMO-SCRIPT.md` |
| Roshan | Data ingestion, API, database, frontend | `core/ingest/`, `core/api/`, `core/audit/`, `domain/corpus.py`, `domain/ui.json`, `scripts/ingest.py`, `data/raw/`, `frontend/` |

Paths under `core/`, `domain/`, `domains/` are inside `backend/app/`. Paths under `scripts/` and `data/` are inside `backend/`.

Shared files, changed only by Akshay: `backend/app/core/contracts.py`, `backend/requirements.txt`, `backend/app/main.py`, `backend/app/config.py`, `.github/`, `.claude/`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`.

If a task needs a change outside your human's folders: stop, say exactly what change is needed and who owns it. Do not make it.

## Before writing code

1. The human starts each task with `/start-task <branch> <what>`. Follow it.
2. For anything touching more than one file, write a plan first: files, functions with exact signatures, tests. Wait for approval.
3. Stub functions (`raise NotImplementedError`) and tests marked `xfail` are the specification. Implement the stub, remove the `xfail` marker, make the test pass.

## How code is written here

- Python 3.11, FastAPI, Pydantic v2. Type hints on every function. A one-line docstring on every public function.
- Shared data shapes come only from `app.core.contracts`. Never redefine `Document`, `Evidence`, `Citation`, `Finding`, `Signal`, `RunContext` or `RunResult`.
- Never change a signature listed in docs/ARCHITECTURE.md. If one must change, stop and tell the human to ask Akshay.
- Touch only the lines the task needs. Never reformat files, reorder imports or rename things you were not asked to change.
- No new dependencies. If one is needed, stop and say which and why (requirements.txt is shared).
- Prefer pure functions: input in, output out, no global state.
- LLM calls only through `app.core.llm.gateway.generate`. Never import a provider SDK anywhere else.
- Settings come from environment variables through `app.config`. Thresholds and keywords come from `domain/policy.yaml`. Never hardcode them.
- Use `logging`, not `print`, in app code.

## Tests

- Tests live in `backend/tests/core/test_<area>_<name>.py` or `backend/tests/domain/`.
- Tests never call the network, a real LLM or a real embedding model. Use the fake LLM and `HashEmbedder`.
- Shared fixtures: `backend/tests/fixtures/` (`sample_documents.json`, `sample_evidence.json`).
- Run them with the backend server stopped: `cd backend`, then `python -m pytest -q`.

## Git: the human runs git, you help

- You never run `git push`, `git reset --hard`, `git rebase`, `git commit --amend` or `git clean`. The settings block them.
- Before a commit is suggested, run `/ready-pr`.
- Commit messages: `<lane>: <what>`, for example `ml: add conformal sets`. No quotes inside the message (PowerShell 5.1 breaks).
- One task = one branch = one pull request. After a pull request is merged, start a new branch from a fresh main.

## Secrets

- Never read, print or write `.env`. Never put a key in code, tests, logs or chat. `.env.example` holds variable names only.

## Windows

- The team uses Windows PowerShell. Give PowerShell commands. Activate the venv with `.venv\Scripts\Activate.ps1`.
- Line endings are handled by `.gitattributes`. Do not change it.

## Talking to the human

- Explain in simple words. The human must be able to explain every line to the judges.
- After finishing a task, explain what changed in 3 to 5 plain bullets. `/explain-change` gives the full version.
- When unsure, ask one short question instead of guessing.

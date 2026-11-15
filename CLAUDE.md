# Team rules for every Claude Code session in this repo

Five people build one app, each with their own Claude Code. These rules keep all of us building the same thing the same way.
They are guidance, not locks: follow them, and when a task needs something they don't cover, ask the human.
The design and the file map are imported below from docs/ARCHITECTURE.md. Read them before writing code.

@docs/ARCHITECTURE.md

## Who you are working for

`CLAUDE.local.md` (repo root, not committed) says which person you are helping and which files they own.
If it is missing, ask the human who they are, and suggest copying theirs from `team/personal/<name>/`.

## The one design rule

Deterministic code decides. The LLM only writes words. Code checks every LLM output before anyone sees it.
Never fake AI results with hardcoded outputs.

## Ownership

Each file has an owner (docs/ARCHITECTURE.md section 3). Work in your human's files.
If a task needs a change in someone else's file, say what change is needed and who owns it, and let the human decide.
Shared files (`backend/app/contracts.py`, `backend/requirements.txt`, `backend/app/config.py`, `.github/`, `.claude/`, `CLAUDE.md`, `docs/ARCHITECTURE.md`) go through Akshay.

## Before writing code

1. The human starts a task with `/start-task <branch> <what>`.
2. For anything touching more than one file, write a short plan first (files, functions, tests) and wait for approval.
3. If a command or script doesn't exist yet, say so. Never invent one.

## How code is written here

- Python 3.12, FastAPI, Pydantic v2. Type hints on every function. A one-line docstring on every public function.
- Shared data shapes come from `app.contracts`. Don't redefine them in other files.
- Touch only the lines the task needs. Don't reformat files, reorder imports or rename things you weren't asked to change.
- No new dependency without asking (requirements.txt is shared).
- Thresholds, keywords and rules live in `backend/app/policy.yaml`. Settings come from environment variables through `app.config`. Never hardcode them.
- LLM calls go through `app.llm.router` (`run_llm`). Never call a provider SDK from anywhere else.
- The LLM chain object is shared across requests: return per-request data from each call; never store it on the shared object.
- Use `logging`, not `print`, in app code.

## Running things (Windows PowerShell)

- Use the venv's Python directly instead of activating it: `.\.venv\Scripts\python.exe` (from `backend`).
- Backend: in `backend`, `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`, then open http://127.0.0.1:8000/docs
- Frontend: in `frontend`, `npm run dev`, then open http://127.0.0.1:5173
- Use `127.0.0.1`, not `localhost` (localhost can resolve to IPv6 and fail).
- Scripts run from `backend`: `.\.venv\Scripts\python.exe scripts\evaluate.py` (and the same for the others).

## Tests

- Stop any running uvicorn first: its reload watcher makes pytest very slow.
- In `backend`: `.\.venv\Scripts\python.exe -m pytest -q`. `tests/conftest.py` already forces offline mode (no LLM calls, hash embedder, temporary database).
- Put new tests in a new file for your area: `backend/tests/test_<area>_<name>.py`.
- Never delete, skip or weaken a test to make it pass. Report what passed and what failed before saying "done".

## Git

- Run git steps one at a time; don't chain them with `;` when a step can fail.
- Check `git status` before switching branches.
- One task = one branch = one pull request. After a pull request is merged, start the next task from a fresh `main`.
- Commit messages: `<lane>: <what>`, for example `ml: add conformal sets`. No quotes inside the message (PowerShell 5.1 breaks).
- Before every commit run `/ready-pr`: it checks files, secrets and tests, and writes the pull request text.
- Push only after the human says yes. Never force-push or `reset --hard` (the settings block these two).
- `gh` isn't installed. Pull request link: https://github.com/akshaykasturi/HCLTECH-Mock/pull/new/<branch>

## Secrets

- Never read, print or write `.env`. Never put a key in code, tests, logs or chat. `.env.example` has variable names and safe defaults only.
- Mask anything key-like in command output, and search the staged changes for keys before every commit.

## Talking to the human

- Explain in simple words. The human must be able to explain every line to the judges.
- After finishing a task, explain what changed in 3 to 5 plain bullets. `/explain-change` gives the full version.
- When unsure, ask one short question instead of guessing.

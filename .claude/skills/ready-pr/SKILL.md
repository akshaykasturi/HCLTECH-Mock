---
description: Check this branch is ready for a pull request and write the pull request text. Run before every commit and pull request.
disable-model-invocation: true
---

## Branch state

!`git status --short --branch`

!`git diff --stat origin/main...HEAD`

Check each item and report pass or fail:

1. Scope: every changed or new file is inside the folders in CLAUDE.local.md, or is the human's own test file. List any file outside them.
2. Secrets and junk: no `.env`, `*.db`, keys, `node_modules`, `.venv`, model files or `__pycache__` in the changes. Search the changes for strings that look like API keys (`AIza`, `gsk_`, `sk-`) and report any match without printing it in full.
3. Contracts: no signature from docs/ARCHITECTURE.md changed. Shared files (`core/contracts.py`, `requirements.txt`, `main.py`, `config.py`, `.claude/`, `CLAUDE.md`) untouched, unless the human is Akshay.
4. Tests: in `backend`, run `python -m pytest -q` and report the summary line. Any `xfail` test for code written in this branch now passes with its marker removed.
5. Noise: no lines changed that the task did not need (no reformatting, no reordered imports).

If anything fails, stop and list the fixes.
If everything passes, write a pull request title (`<lane>: <what>`) and a description that follows `.github/pull_request_template.md`, ready to paste.
Then show the exact commands for the human to run: `git add` with each file by name, `git commit -m "<title>"`, `git push -u origin <branch>`. Never run `git push` yourself.

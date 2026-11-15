---
description: Test and check this branch, then commit, push and print the pull request link.
disable-model-invocation: true
---

## Branch state

!`git status --short --branch`

!`git diff --stat origin/main...HEAD`

1. Tests: with uvicorn stopped, in `backend` run `.\.venv\Scripts\python.exe -m pytest -q` and report the summary line. If the frontend changed, run `npm run lint` and `npm run build` in `frontend`.
2. Secrets and junk: no `.env`, `*.db`, keys, `node_modules`, `.venv`, `data/index/`, `__pycache__` in the changes. Search the changes for key-like strings (`AIza`, `gsk_`, `sk-`) and report any match without printing it in full.

If something fails, list the fixes and stop.
If everything passes, without asking first: run `git add` with each file by name, then `git commit -m "<lane>: <what>"`, then `git push -u origin <branch>`, one at a time.
Write a short pull request description following `.github/pull_request_template.md`.
Finish with the link: https://github.com/akshaykasturi/HCLTECH-Mock/pull/new/<branch>

---
description: Check this branch is ready, write the pull request text, then commit and push with the human's OK.
disable-model-invocation: true
---

## Branch state

!`git status --short --branch`

!`git diff --stat origin/main...HEAD`

Check each item and report pass or fail:

1. Files: list every changed file and its owner from docs/ARCHITECTURE.md. Point out any file the human doesn't own, so they can check the owner knows.
2. Secrets and junk: no `.env`, `*.db`, keys, `node_modules`, `.venv`, `data/index/`, `__pycache__` in the changes. Search the changes for key-like strings (`AIza`, `gsk_`, `sk-`) and report any match without printing it in full.
3. Shared files: if `contracts.py`, `requirements.txt`, `config.py`, `.claude/` or `CLAUDE.md` changed, remind the human to tell Akshay.
4. Tests: with uvicorn stopped, in `backend` run `.\.venv\Scripts\python.exe -m pytest -q` and report the summary line. If the frontend changed, run `npm run lint` and `npm run build` in `frontend`.
5. Noise: no lines changed that the task didn't need (no reformatting, no reordered imports).

If something fails, list the fixes and stop.
If everything passes, write the pull request title (`<lane>: <what>`) and a description following `.github/pull_request_template.md`.
Then ask the human: "Commit and push now?" If they say yes, run `git add` with each file by name, then `git commit -m "<title>"`, then `git push -u origin <branch>`, one at a time.
Finish with the link: https://github.com/akshaykasturi/HCLTECH-Mock/pull/new/<branch>

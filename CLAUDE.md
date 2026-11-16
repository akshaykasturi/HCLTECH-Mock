# How we work in this repo

We are building UC4: an API failure diagnosis assistant (HCLTech hackathon mock).
Read docs/PLAN.md first. Data is described in backend/data/eval/uc4/DATA_CARD.md.

## Design rules

- Code decides; the LLM only explains; code checks the LLM's output before anyone sees it.
- Never show a probable cause as confirmed. Causes are "likely" or "probable".
- Never expose secrets. The fake tokens, keys and emails in `backend/data/raw/uc4/logs/requests.jsonl` are test material for masking: don't remove, change or print them.
- Use the data's own field names (`route`, `correlation_id`, `kind`/`target` in metrics, `case_id`...). Don't rename them.
- Tuning uses the validation split only. Final numbers use the test split only.
- Never fake AI results with hardcoded outputs.

## Git

- One branch per piece of work. Pull main before starting (`/start-task`).
- Run `/ready-pr` when done; merge your pull request when CI is green.
- Commit messages: `<area>: <what>`, no quotes inside. Never force-push.
- `gh` isn't installed. Pull request link: https://github.com/akshaykasturi/HCLTECH-Mock/pull/new/<branch>

## Running things

- Python 3.12, Windows PowerShell.
- Call the venv's Python directly, from `backend`: `.\.venv\Scripts\python.exe -m pytest -q`.
- Use `127.0.0.1`, not `localhost`.
- Never read or print `.env`; never put a key in code, tests, logs or chat.
- No new dependency without saying so in the pull request (`backend/requirements.txt`).

## Talking to the human

- Explain every change simply: the human must be able to explain it to the judges.
- When unsure, ask one short question instead of guessing.

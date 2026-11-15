# Team kit

These files make every teammate's Claude Code follow the same design and the same habits. They are guidance: anyone can edit any file, push their own branch and merge their own pull request once CI is green. Only force-push and reading `.env` are blocked.

| File | What it does |
|---|---|
| `CLAUDE.md` | Team rules every Claude reads at the start of every session; it pulls in `docs/ARCHITECTURE.md` |
| `docs/ARCHITECTURE.md` | The pipeline, every file with its lead (who to ask), the new files to create |
| `team/TASKS.md` | Each person's tasks in order |
| `.claude/rules/*.md` | Technical rules, loaded when Claude opens a file in that area |
| `.claude/skills/` | `/start-task`, `/ready-pr`, `/explain-change` |
| `.claude/settings.json` | Lets everyday git, test, npm and pip commands run without asking |
| `team/personal/<name>/CLAUDE.local.md` | Tells your Claude who you are (copy it to the repo root; it is never committed) |

## Set-up (everyone, once)

In PowerShell, in the repo folder:

```
git switch main
git pull
copy team\personal\<your-name>\CLAUDE.local.md CLAUDE.local.md
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm install
cd ..
```

Put your own free Gemini and Groq keys in `backend\.env`. Never commit it.
Then start Claude Code from the repo root: `claude`.

## Every task

1. `/start-task <branch> Task <id> from team/TASKS.md`
2. Read the changes (`git diff`) until you understand them.
3. `/ready-pr`: tests, checks, commit, push, link.
4. Open the link, create the pull request, merge it when CI is green.
5. `/explain-change` to practise explaining it.

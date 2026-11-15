# Team kit

These files make every teammate's Claude Code follow the same design and the same habits. They are guidance: nothing stops you from working, pushing or editing.

| File | What it does |
|---|---|
| `CLAUDE.md` | Team rules every Claude reads at the start of every session; it pulls in `docs/ARCHITECTURE.md` |
| `docs/ARCHITECTURE.md` | The pipeline, every file with its owner, the new files to create, what changes for a new problem |
| `team/TASKS.md` | Each person's tasks in order |
| `.claude/rules/*.md` | Lane rules, loaded when Claude opens a file in that lane |
| `.claude/skills/` | `/start-task`, `/ready-pr`, `/explain-change` |
| `.claude/settings.json` | Lets everyday git and test commands run without asking; blocks only force-push, `reset --hard` and reading `.env` |
| `.github/pull_request_template.md` | Same checklist on every pull request |
| `team/personal/<name>/CLAUDE.local.md` | Tells your Claude who you are and which files are yours (copy it to the repo root; it is never committed) |

## Set-up (everyone, once)

In PowerShell, in the repo folder:

```
git switch main
git pull
copy team\personal\<your-name>\CLAUDE.local.md CLAUDE.local.md
```

Backend:

```
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe -m pytest -q
cd ..
```

Put your own free Gemini and Groq keys in `backend\.env`. Never commit it.

Frontend:

```
cd frontend
npm install
cd ..
```

Then start Claude Code from the repo root: `claude`. Type `/` and check that `start-task`, `ready-pr` and `explain-change` are listed.

## Every task

1. `/start-task <branch> Task <id> from team/TASKS.md`
2. Read and approve the plan.
3. Let it build; read the changes (`git diff`) until you understand them.
4. `/ready-pr`: it checks everything, writes the pull request text, and commits and pushes when you say yes.
5. Open the link it gives you, create the pull request, post it in the group.
6. `/explain-change` to practise explaining it.

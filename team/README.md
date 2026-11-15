# Team kit: how to install it

This kit makes every teammate's Claude Code follow the same rules, read the same design and stay inside its owner's folders.

## What is in it

| File | What it does | Committed? |
|---|---|---|
| `CLAUDE.md` | Team rules every Claude reads at the start of every session | Yes |
| `docs/ARCHITECTURE.md` | The design: pipeline, contracts, every module with its owner and signature | Yes |
| `.claude/settings.json` | Blocks `git push`, force pushes, history rewrites and reading `.env`; allows tests and safe git commands | Yes |
| `.claude/rules/*.md` | Lane rules, loaded only when Claude opens a file in that lane | Yes |
| `.claude/skills/` | `/start-task`, `/ready-pr`, `/explain-change` | Yes |
| `.github/pull_request_template.md` | Every pull request uses the same checklist | Yes |
| `docs/DECISIONS.md`, `docs/DAY-LOG.md` | Why we chose things; what was built when | Yes |
| `team/personal/<name>/CLAUDE.local.md` | Tells your Claude who you are and which folders are yours | Copied to your repo root, never committed |
| `team/personal/<name>/settings.local.json` | Stops your Claude from editing other people's folders | Copied into `.claude/`, never committed |

## Akshay, once

1. Copy everything in this kit into the repo root, keeping the folders (`.claude/`, `docs/`, `.github/`, `team/`, `CLAUDE.md`).
2. Append `team/gitignore-additions.txt` to `.gitignore`.
3. Commit and push it (`chore: add team kit`), through a pull request if main is protected.
4. Run Prompt A from `team/AKSHAY-PROMPTS.md`, merge it, then tell the team to start.
5. Run Prompt B while the team works.

## Everyone, once (after Akshay says go)

```
git switch main
git pull
copy team\personal\<your-name>\CLAUDE.local.md CLAUDE.local.md
copy team\personal\<your-name>\settings.local.json .claude\settings.local.json
git status
```

`git status` must NOT list `CLAUDE.local.md` or `.claude/settings.local.json`; if it does, tell Akshay (the `.gitignore` lines are missing).

Then start Claude Code from the repo root (`claude`), so it loads `CLAUDE.md` and your local files. Restart it whenever you pull changes to `.claude/`.

## Every task

1. `/start-task <branch> <what>`, for example `/start-task ml/conformal implement conformal sets`
2. Read and approve the plan.
3. Let it implement; read the diff (`git diff`) and make sure you understand it.
4. `/ready-pr`, then run the commands it gives you and open the pull request.
5. `/explain-change` to practise explaining it.

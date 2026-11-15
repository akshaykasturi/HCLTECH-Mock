---
description: Start a new piece of work on a fresh branch. Run at the start of every task.
disable-model-invocation: true
argument-hint: <branch-name> <what to build>
---

## Repo state

!`git status --short --branch`

Task: $ARGUMENTS

1. From CLAUDE.local.md, say who the human is and which files they own. If it is missing, ask who they are.
2. If the repo state above shows uncommitted changes, ask what to do with them (commit them, or `git stash`) before going on.
3. Run `git switch main`, then `git pull`, then `git switch -c <branch-name>` (the first word of the task), one at a time.
4. Read the parts of docs/ARCHITECTURE.md and the `.claude/rules/` file that cover this task. If the task is in `team/TASKS.md`, read that row.
5. Write a short plan: files to create or change (say if any belong to someone else), functions, and the tests you will add.
6. Wait for the human to approve the plan before editing files.

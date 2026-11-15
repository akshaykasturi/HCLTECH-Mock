---
description: Start a new piece of work on a fresh branch inside your own lane. Run at the start of every task.
disable-model-invocation: true
argument-hint: <branch-name> <what to build>
---

## Repo state

!`git status --short --branch`

Task: $ARGUMENTS

Follow these steps in order:

1. From CLAUDE.local.md, say who the human is and list the folders they own. If CLAUDE.local.md is missing, stop and ask them to copy it from `team/personal/<name>/`.
2. If the repo state above shows uncommitted changes, stop and ask what to do with them (commit them, or `git stash`).
3. Run `git switch main`, then `git pull`, then `git switch -c <branch-name>` using the first word of the task. Show the output.
4. Read docs/ARCHITECTURE.md sections 2 and 3 and the `.claude/rules/` file for this lane. Find the stub functions and `xfail` tests for this task.
5. Write a short plan: files to create or change (every one inside the human's folders, or their own test files), each function with its exact signature from ARCHITECTURE.md, the tests you will make pass, and anything needed from another person.
6. Stop and wait for the human to approve the plan. Do not edit any file before approval.

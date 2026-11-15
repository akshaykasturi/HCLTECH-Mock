# Akshay's two set-up prompts for Claude Code

Run both in plan mode (Shift+Tab until it says plan mode), from the repo root. Read the plan before approving.
Do not install your own `team/personal/akshay/settings.local.json` until both pull requests are merged: these two prompts must create files in everyone's folders.

---

## Prompt A: skeleton (about 30 minutes, merge before anyone starts)

```
You are setting up the shared skeleton for a 5-person hackathon team. Read CLAUDE.md and docs/ARCHITECTURE.md fully first; they are the specification.

In this pull request, create ONLY new files. Do not move, rename or edit existing app code (the only existing file you may edit is .gitignore).

1. backend/app/core/__init__.py and an __init__.py in every core subfolder named in ARCHITECTURE.md section 3 (ingest, retrieval, ml, analysis, llm, llm/providers, guardrails, evals, audit, api).
2. backend/app/core/contracts.py implementing section 2 exactly: Pydantic v2 models and the DomainPack dataclass. This file is real code, not a stub.
3. For every module in section 3 with status "new": a stub file with the exact signatures and type hints, a docstring saying what the function must do (from the table and the matching .claude/rules file), and a body of `raise NotImplementedError`. Every stub must import cleanly. Skip modules with status "port": the next pull request moves existing code there.
4. For every stub function, one or two tests in backend/tests/core/test_<area>_<module>.py marked `@pytest.mark.xfail(reason="not implemented yet", strict=False)`. Each test calls the function with a small realistic input and asserts the behaviour from the docstring. These tests are the specification for the owner, so write the assertions carefully and keep them simple.
5. backend/tests/fixtures/sample_documents.json (3 short documents with headings, one containing numbers like "rate limit 100 requests per minute") and sample_evidence.json (5 Evidence items in the contracts shape, ids E1 to E5), plus conftest.py fixtures that load them as model objects.
6. backend/app/domain/ with the 8 files from section 5 as templates: a docstring saying what goes in the file and who owns it, TODO markers, nothing imported by the running app yet.
7. Append the lines in team/gitignore-additions.txt to .gitignore.

Rules: the existing app must still start and all existing tests must still pass. The new xfail tests count as expected failures, so CI stays green. No new dependencies.
At the end, run `python -m pytest -q` in backend and show the summary line. Then print a table: owner, stub file, functions, test file, so I can give each teammate their first task. Do not commit.
```

After it finishes: run `/ready-pr`, commit, push, open the pull request, wait for green CI, merge, then tell the team to pull and start.

---

## Prompt B: port the working code (about 60 minutes, while the team implements stubs)

```
Move the existing working ticket-assistant code into the new structure, with behaviour unchanged. Read docs/ARCHITECTURE.md section 3: every module with status "port" gets its code from the existing app. Map by purpose; the old file names may differ from these:

- classification (old pipeline/classify.py) -> core/ml/classifier.py
- search and embeddings (old pipeline/retrieve.py and embedding code) -> core/retrieval/index.py (split into helper files inside core/retrieval/ if it is long)
- gate rules (old pipeline/gate.py) -> core/gate.py
- redaction (old pipeline/redact.py) -> core/guardrails/redact.py; injection, hazard and vague-input rules -> core/guardrails/input_checks.py
- citation checking (old pipeline/verify.py) -> core/guardrails/citations.py
- LLM providers and router (old llm/) -> core/llm/providers/ and core/llm/router.py
- database and audit code -> core/audit/store.py; API routes from main.py -> core/api/routes.py (main.py keeps creating the app and includes the router)
- the orchestrator -> core/pipeline.py (generic runner) plus backend/app/domains/tickets/ (ticket models, prompts, policy.yaml, ui.json, data loading, ticket-specific steps)
- backend/app/domain/__init__.py points DOMAIN at the tickets pack for now

Use `git mv` so history is kept. Fix imports. Keep the public behaviour identical: same API paths, same response shapes, the frontend keeps working.
Where a ported function's name differs from its ARCHITECTURE.md signature, add a thin function with the ARCHITECTURE.md signature that calls the old code. Do not rewrite the logic.
Do not touch any stub file or xfail test created by the skeleton pull request.
All existing tests must pass; update import paths in tests only. Show the pytest summary and list every moved file (old path -> new path). Do not commit.
```

Send the plan for Prompt B to Claude chat before approving it.

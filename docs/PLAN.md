# Plan: UC4 API failure diagnosis

## The idea

```
case -> hide secrets -> collect evidence -> yes/no signals -> failure class -> rank causes
     -> not enough evidence? CLARIFY with what's missing (no LLM)
     -> LLM writes the report -> code checks the report -> API + screen + reviewer feedback
evaluation runs the same steps over the validation and test splits
```

1. **Case**: a failure case from `backend/data/eval/uc4/cases.jsonl` (route, `focal_correlation_id`, `onset_ts`, time window).
2. **Hide secrets**: mask tokens, API keys, emails and IPs before anything else reads the text.
3. **Collect evidence**: request logs in the window; metrics for the route and its dependencies compared with the hour before; deploys and config changes near the onset; search over the API docs.
4. **Yes/no signals**: e.g. "401 seen", "token older than its lifetime", "dependency latency spiked", "deploy just before onset".
5. **Failure class**: authentication, authorization, validation, rate_limit, timeout, dependency, server_error.
6. **Rank causes**: each likely cause with the evidence that supports it AND the evidence against it, plus a confidence.
7. **Not enough evidence**: answer CLARIFY and list the missing information. No LLM call.
8. **LLM report**: the LLM only writes the words, from the ranked causes and evidence it is given. Safe, read-only verification steps; ESCALATE when a step needs privileged access.
9. **Code checks the report**: citations exist, numbers match the evidence, nothing says "confirmed" without proof, no destructive steps, no secrets.
10. **API + screen + feedback**: the reviewer can confirm, reject or annotate the report (audit-friendly, FR-08).
11. **Evaluation**: top-1, top-3, MRR, class accuracy, CLARIFY rate, with confidence intervals (`backend/app/analysis/stats.py`).

Submission: working app, evaluation report, 5 worked examples (4xx, 5xx, auth, timeout, rate limit; listed in the data card), README.

## Who leads what

Lead = who builds it first and who to ask. Anyone can work on anything.

- **Akshay**: evidence, doc search, ranking, gate, pipeline, merges.
- **Atheesha**: secret masking, LLM report, output checks, attack tests.
- **Raswanth**: signals and failure classifier.
- **Akhilesh**: data, evaluation, pitch.
- **Roshan**: loaders, API, screen.

## Where things go

- Code: `backend/app/uc4/`
- Tests: `backend/tests/` (`test_<area>_<name>.py`)
- Scripts: `backend/scripts/`
- Frontend: `frontend/`
- Data: `backend/data/raw/uc4/` (logs, metrics, changes, API docs) and `backend/data/eval/` (cases, splits, classifier files)

## Decided so far

These are ideas, not fixed rules. Agree on shared shapes (case, evidence item, cause, report) in the group and write them here as they are decided.

- (nothing yet)

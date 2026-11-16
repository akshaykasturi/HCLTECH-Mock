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

- **EvidenceItem shape** (`backend/app/uc4/models.py`, built by `collect_evidence(case)` in `backend/app/uc4/evidence.py`):
  - `id`: stable, so the report can cite it: `request:<correlation_id>`, `traffic:window`, `metric:endpoint:<route>`, `metric:service:<name>`, `change:<ts>:<service>`, `missing:<what>`.
  - `kind`: `request` | `traffic` | `metric` | `change` | `missing`.
  - `text`: one readable line with the numbers (what the LLM sees and quotes).
  - `data`: the same numbers as a dict (what signals, ranking and the output check use; never parse `text`).
  - Window = `[window_start, window_end]`; baseline = the 60 minutes before `window_start`; changes from 60 minutes before `onset_ts` to `window_end`. Sizes live in `backend/app/uc4/settings.yaml`.
  - Evidence never reads labels and never copies `request_headers`; error messages are masked (emails, tokens, keys, IPs).
  - Try it: `.\.venv\Scripts\python.exe scripts\show_evidence.py UC4-0050` (add `--data` for the numbers).
- **Report shape** (`backend/app/uc4/report_models.py`, checked by `check_report(report, evidence, allowed_causes)` in `backend/app/uc4/checks.py` before anyone sees it):
  - `Report`: `case_id`, `outcome` (`RECOMMEND` | `CLARIFY` | `ESCALATE`), `summary`, `causes`, `verification_steps`, `escalation`, `missing_info`.
  - `ReportCause`: `cause` (one of the ranked causes), `likelihood` (`likely` | `probable` | `possible`, never confirmed), `explanation`, `supporting` and `contradicting` citations.
  - `Citation`: `evidence_id` (an EvidenceItem `id`) + `quote` copied from that item's `text`.
  - `Step`: a read-only check (`action`, `why`, `cites`); changing actions (restart, rotate, roll back...) go in `Escalation` (`needed`, `team`, `reason`).
  - Checks: citations exist and quotes match, only ranked causes, numbers match the cited evidence, no "confirmed" wording, no changing steps, no secrets, outcome consistent. Each returns `Finding`s (`code`, `severity`, `message`, `where`); `apply_findings` removes blocked parts (no cause left -> CLARIFY). `groundedness` = verified citations / all citations. Word lists in `backend/app/uc4/checks.yaml`.

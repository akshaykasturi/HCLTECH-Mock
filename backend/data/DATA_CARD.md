# Data card

All data is **synthetic**, produced by `scripts/generate_data.py --seed 42` from 39 scenarios
in `scripts/scenarios.py`. Each scenario is one root cause with typical symptoms and a fix.

| File | Rows | Use |
|---|---|---|
| historical_tickets.csv | 1200 | Retrieval corpus, classifier training |
| kb_articles.json | 41 | Approved runbooks (+2 draft/superseded that must never be cited) |
| test/holdout_tickets.csv | 120 | Unseen generator tickets, separate random stream, later dates |
| test/novel_tickets.csv | 10 | No matching history: expected ESCALATE or CLARIFY |
| test/handwritten_tickets.csv | team-written | Independent tickets written by hand |

Historical tickets by category:

| Category | Count |
|---|---|
| Access & Identity | 186 |
| Application Errors | 186 |
| Email & Collaboration | 186 |
| Hardware | 186 |
| Network | 186 |
| Security | 120 |
| Software | 150 |

Historical tickets by priority:

| Priority | Count |
|---|---|
| P1 | 159 |
| P2 | 299 |
| P3 | 537 |
| P4 | 205 |

328 historical tickets contain synthetic personal data (email, phone, IP) to exercise redaction.

**Limits (stated honestly):** the holdout set comes from the same scenarios as the training data, so its
scores are optimistic. Hand-written, LLM-paraphrased and novel tickets are reported separately in the
evaluation report because they are the real test. `scenario_id` is for evaluation only.

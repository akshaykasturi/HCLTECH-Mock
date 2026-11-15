---
paths:
  - "backend/tests/**"
---

# Tests

- New tests go in a new file for your area: `test_<area>_<name>.py`.
- No network, no real LLM, no real embedding model: `conftest.py` forces offline mode.
- One behaviour per test, named after it: `test_numbers_flags_number_missing_from_source`.
- Never delete, skip or weaken a test to make it pass.

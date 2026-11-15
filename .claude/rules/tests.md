---
paths:
  - "backend/tests/**"
---

# Tests

- File names: `test_<area>_<name>.py`. The owner of the code owns its test file.
- No network, no real LLM, no real embedding model: use the fake LLM and `HashEmbedder`.
- One behaviour per test, named after it: `test_numbers_flags_number_missing_from_evidence`.
- `xfail` markers in skeleton tests are the specification: remove the marker when you implement the function.
- Use the shared fixtures in `backend/tests/fixtures/`. Add new fixture files only for your own area.

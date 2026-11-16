# UC4: API failure diagnosis assistant

HCLTech hackathon mock. Given an API failure case, the assistant reads request logs, endpoint metrics, deploys and API docs, and returns a failure class, ranked likely causes with supporting and contradicting evidence, a confidence, missing information and safe verification steps. Plan: [docs/PLAN.md](docs/PLAN.md).

## Data

Fully synthetic (fictional "NovaPay Commerce API"). See [backend/data/eval/uc4/DATA_CARD.md](backend/data/eval/uc4/DATA_CARD.md).

- `backend/data/raw/uc4/`: API docs, request logs, metrics, deploys and changes
- `backend/data/eval/`: 90 labelled cases, splits, classifier files

The request logs contain fake tokens, keys and emails on purpose, to test secret masking.

## Set up (Windows PowerShell)

```
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

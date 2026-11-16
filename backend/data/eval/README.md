# Evaluation data

Owner: Akhilesh. Full description of the dataset: [uc4/DATA_CARD.md](uc4/DATA_CARD.md).

The UC4 data is **fully synthetic** (fictional "NovaPay Commerce API", CC0), made by a seeded generator (`uc4-gen-1.0`, seed 42). The raw corpus and logs it is built on are in `backend/data/raw/uc4/`.

## Splits (cases)

Source: the `split` field of `uc4/cases.jsonl`. The generator assigns it per cause (14 causes, 6 cases each) and for the 6 insufficient-evidence cases. Case lists, one `case_id` per line, are in `uc4/splits/`.

| Split | File | Cases | How it was made | Use |
|---|---|---|---|---|
| train | `splits/train.txt` | 43 | per cause 1 easy + 1 medium + 1 hard; plus 1 insufficient | training |
| validation | `splits/validation.txt` | 15 | per cause 1 medium; plus 1 insufficient | tuning only (thresholds, conformal calibration) |
| test | `splits/test.txt` | 32 | per cause 1 easy + 1 hard; plus 4 insufficient | final numbers only, never for a decision |

Checked when the splits were written: no case is in two splits and all 90 cases appear exactly once.

**"calibration" = validation.** The CSV files and `cases.jsonl` keep the generator's name "calibration". In this repo that split is the validation split.

## Classifier files

`uc4/classifier_{train,calibration,test}.csv` (`case_id,is_focal,text,label`): up to 12 failing log lines per case, 427 / 133 / 303 rows. They are grouped by case: every `case_id` in each file belongs to the matching split above (checked).

## Search evaluation

`uc4/retrieval_gold.jsonl`: 20 hand-written engineer questions about the docs in `backend/data/raw/uc4/api_docs/`, each with `query`, `gold_doc_ids` and `note`. A doc id is the file path relative to `api_docs/` without the extension (`rate-limits`, `endpoints/orders`, `legacy/rate-limits-v1`). Gold = every doc that contains the answer. It includes 3 paraphrased questions that avoid the docs' wording and 2 questions with no answer (`gold_doc_ids: []`).

## Where the manifest's files are

`uc4/manifest.json` is unchanged from the generator, so its paths are relative to the original single `uc4/` folder:

| Manifest path | Path in this repo |
|---|---|
| `cases/cases.jsonl` | `backend/data/eval/uc4/cases.jsonl` |
| `cases/classifier_train.csv` | `backend/data/eval/uc4/classifier_train.csv` |
| `cases/classifier_calibration.csv` | `backend/data/eval/uc4/classifier_calibration.csv` |
| `cases/classifier_test.csv` | `backend/data/eval/uc4/classifier_test.csv` |
| `logs/requests.jsonl` | `backend/data/raw/uc4/logs/requests.jsonl` |
| `metrics/metrics.csv` | `backend/data/raw/uc4/metrics/metrics.csv` |
| `changes/changes.jsonl` | `backend/data/raw/uc4/changes/changes.jsonl` |

The copies are byte-for-byte the generator's files. One catch: the generator wrote the 4 CSV files (`classifier_train/calibration/test.csv`, `metrics.csv`) with Windows line endings (CRLF), and this repo's `.gitattributes` stores every text file with LF. So the committed CSVs have LF endings and their SHA-256 no longer matches the manifest. The rows and values are identical; only the line endings differ. The 3 JSONL files still match the manifest exactly.

## Fake secrets, on purpose

`backend/data/raw/uc4/logs/requests.jsonl` contains **fake** JWT-shaped bearer tokens, `nvp_live_` / `nvp_test_` keys and `@example.*` emails so redaction can be tested. None of them is real.

"""Smoke tests: the UC4 dataset is present and loads."""
import csv
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
EVAL = DATA / "eval" / "uc4"
RAW = DATA / "raw" / "uc4"


def _case_ids() -> list[str]:
    """Return every case_id in cases.jsonl, in file order."""
    with open(EVAL / "cases.jsonl", encoding="utf-8") as f:
        return [json.loads(line)["case_id"] for line in f if line.strip()]


def test_cases_file_has_90_cases() -> None:
    ids = _case_ids()
    assert len(ids) == 90
    assert len(set(ids)) == 90


def test_every_split_case_id_exists_in_cases() -> None:
    known = set(_case_ids())
    split_files = sorted((EVAL / "splits").glob("*.txt"))
    assert split_files, "no split files found"
    for path in split_files:
        ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert ids, f"{path.name} is empty"
        missing = [i for i in ids if i not in known]
        assert not missing, f"{path.name} has unknown case ids: {missing[:5]}"


def test_request_logs_load() -> None:
    with open(RAW / "logs" / "requests.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert rows
    assert {"ts", "correlation_id", "route", "status"} <= rows[0].keys()


def test_metrics_load() -> None:
    with open(RAW / "metrics" / "metrics.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert {"ts", "kind", "target", "rps", "error_rate", "p50_ms", "p95_ms"} <= rows[0].keys()

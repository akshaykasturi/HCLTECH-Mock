"""Checks that the synthetic dataset is valid, reproducible and free of train/test leakage."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from generate_data import generate  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_counts_and_ids(tmp_path):
    stats = generate(42, tmp_path)
    hist = read_csv(tmp_path / "historical_tickets.csv")
    assert len(hist) == stats["historical"] == 1200
    assert len({r["ticket_id"] for r in hist}) == len(hist)  # unique ids
    assert all(r["status"] == "Resolved" and r["resolution_notes"] for r in hist)


def test_every_scenario_has_history(tmp_path):
    generate(42, tmp_path)
    hist = read_csv(tmp_path / "historical_tickets.csv")
    seen = {r["scenario_id"] for r in hist}
    assert seen == {s["id"] for s in SCENARIOS}


def test_reproducible(tmp_path):
    generate(42, tmp_path / "a")
    generate(42, tmp_path / "b")
    a = (tmp_path / "a" / "historical_tickets.csv").read_text(encoding="utf-8")
    b = (tmp_path / "b" / "historical_tickets.csv").read_text(encoding="utf-8")
    assert a == b


def test_no_leakage_between_history_and_holdout(tmp_path):
    generate(42, tmp_path)
    hist = {r["description"].lower() for r in read_csv(tmp_path / "historical_tickets.csv")}
    holdout = read_csv(tmp_path / "test" / "holdout_tickets.csv")
    assert not [r for r in holdout if r["description"].lower() in hist]
    # holdout tickets expose input fields only, never labels
    assert "category" not in holdout[0] and "scenario_id" not in holdout[0]


def test_holdout_is_later_than_history(tmp_path):
    generate(42, tmp_path)
    last_hist = max(r["created_at"] for r in read_csv(tmp_path / "historical_tickets.csv"))
    first_test = min(r["created_at"] for r in read_csv(tmp_path / "test" / "holdout_tickets.csv"))
    assert first_test > last_hist


def test_labels_cover_every_test_ticket(tmp_path):
    generate(42, tmp_path)
    labels = {r["test_id"] for r in read_csv(tmp_path / "test" / "labels.csv")}
    tests = [r["test_id"] for r in read_csv(tmp_path / "test" / "holdout_tickets.csv")]
    tests += [r["test_id"] for r in read_csv(tmp_path / "test" / "novel_tickets.csv")]
    assert labels == set(tests)


def test_lookalikes_point_to_real_scenarios(tmp_path):
    ids = {s["id"] for s in SCENARIOS}
    for s in SCENARIOS:
        if s.get("lookalike"):
            assert s["lookalike"] in ids, s["id"]


def test_kb_has_non_approved_articles(tmp_path):
    generate(42, tmp_path)
    kb = json.loads((tmp_path / "kb_articles.json").read_text(encoding="utf-8"))
    statuses = {a["status"] for a in kb}
    assert {"approved", "draft", "superseded"} <= statuses


def test_handwritten_file_is_never_overwritten(tmp_path):
    generate(42, tmp_path)
    path = tmp_path / "test" / "handwritten_tickets.csv"
    path.write_text(path.read_text(encoding="utf-8") + "HW0001,x,y,,prod,,,,,,\n", encoding="utf-8")
    generate(42, tmp_path)
    assert "HW0001" in path.read_text(encoding="utf-8")

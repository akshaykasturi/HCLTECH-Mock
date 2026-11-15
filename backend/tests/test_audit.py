"""Audit log + analyst feedback. Uses the temporary SQLite database set in conftest.py.
Tests share that database, so stats checks compare counts before and after instead of absolute totals."""
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import BACKEND_DIR
from app.db.session import get_engine, normalize_url
from app.main import app

client = TestClient(app)

VPN = {"title": "VPN not connecting",
       "description": "GlobalProtect shows certificate error from home. Worked last week."}


def analyze(ticket=VPN, **headers) -> dict:
    body = client.post("/api/analyze", json=ticket, headers=headers).json()
    assert body["ok"], body
    return body["data"]


def test_tests_do_not_use_the_real_database():
    assert "app.db" not in str(get_engine().url) and "test.db" in str(get_engine().url)


def test_analyze_saves_a_row():
    data = analyze(**{"X-Request-ID": "audit-req-1"})
    body = client.get(f"/api/analyses/{data['analysis_id']}").json()
    assert body["ok"] and body["error"] is None
    rec = body["data"]
    assert rec["analysis_id"] == data["analysis_id"] and rec["request_id"] == "audit-req-1"
    assert rec["outcome"] == data["outcome"] and rec["reasons"] == data["reasons"]
    assert rec["generator"] == data["recommendation"]["generator"] == "extractive"
    assert rec["feedback"] == []
    listed = client.get("/api/analyses", params={"outcome": data["outcome"], "limit": 200}).json()["data"]
    assert data["analysis_id"] in {a["analysis_id"] for a in listed}
    assert all(a["outcome"] == data["outcome"] for a in listed)


def test_raw_email_never_reaches_the_database():
    data = analyze({"title": "Locked out jane.doe@corp.example",
                    "description": "my AD account keeps getting locked, mail me at x.y@acmecorp.example"})
    fb = client.post(f"/api/analyses/{data['analysis_id']}/feedback",
                     json={"verdict": "useful", "target": "recommendation",
                           "comment": "confirmed with x.y@acmecorp.example"}).json()
    assert fb["ok"]
    with get_engine().connect() as conn:
        dump = str(conn.execute(text("SELECT * FROM analyses")).all()) + \
               str(conn.execute(text("SELECT * FROM feedback")).all())
        title = conn.execute(text("SELECT title FROM analyses WHERE id = :id"),
                             {"id": data["analysis_id"]}).scalar_one()
    assert "jane.doe@corp.example" not in dump and "x.y@acmecorp.example" not in dump
    assert title == "Locked out [EMAIL]"


def test_feedback_is_saved_and_returned():
    data = analyze()
    target = f"match:{data['matches'][0]['source_id']}"
    r = client.post(f"/api/analyses/{data['analysis_id']}/feedback",
                    json={"verdict": "incorrect", "target": target, "comment": "wrong app", "reviewer": "analyst1"})
    assert r.status_code == 200 and r.json()["ok"]
    saved = r.json()["data"]
    assert saved["verdict"] == "incorrect" and saved["target"] == target and saved["id"]
    rec = client.get(f"/api/analyses/{data['analysis_id']}").json()["data"]
    assert [f["id"] for f in rec["feedback"]] == [saved["id"]]
    assert rec["feedback"][0]["reviewer"] == "analyst1"


@pytest.mark.parametrize("payload", [
    {"verdict": "great", "target": "recommendation"},          # unknown verdict
    {"verdict": "useful", "target": "the whole thing"},        # malformed target
    {"verdict": "useful", "target": "match:INC_NOT_RETRIEVED"},  # not a match of this analysis
])
def test_bad_feedback_gives_validation_error(payload):
    data = analyze()
    r = client.post(f"/api/analyses/{data['analysis_id']}/feedback", json=payload)
    body = r.json()
    assert r.status_code == 422 and body["ok"] is False and body["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_id_gives_404_not_found():
    r = client.get("/api/analyses/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND" and r.json()["request_id"]
    r = client.post("/api/analyses/does-not-exist/feedback", json={"verdict": "useful", "target": "recommendation"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_list_rejects_bad_outcome_filter():
    body = client.get("/api/analyses", params={"outcome": "MAYBE"}).json()
    assert body["ok"] is False and body["error"]["code"] == "VALIDATION_ERROR"


def test_stats_counts_are_correct():
    before = client.get("/api/stats").json()["data"]
    tickets = [VPN, {"title": "help", "description": "It is not working."},
               {"title": "Printer smells", "description": "Printer on floor 3 smells like burning plastic."}]
    results = [analyze(t) for t in tickets]
    for verdict in ("useful", "useful", "unresolved"):
        assert client.post(f"/api/analyses/{results[0]['analysis_id']}/feedback",
                           json={"verdict": verdict, "target": "recommendation"}).json()["ok"]
    after = client.get("/api/stats").json()["data"]

    assert after["total_analyses"] - before["total_analyses"] == 3
    expected = Counter(r["outcome"] for r in results)
    for outcome in ("RECOMMEND", "CLARIFY", "ESCALATE"):
        delta = after["by_outcome"].get(outcome, 0) - before["by_outcome"].get(outcome, 0)
        assert delta == expected[outcome], outcome
    for verdict, n in {"useful": 2, "unresolved": 1, "incorrect": 0}.items():
        assert after["by_verdict"].get(verdict, 0) - before["by_verdict"].get(verdict, 0) == n, verdict
    assert sum(after["generator_share"].values()) == pytest.approx(1.0, abs=0.01)
    assert set(after["generator_share"]) <= {"extractive", "none"}  # tests run without an LLM


def test_database_failure_still_returns_the_analysis(monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("INSERT INTO analyses", {}, Exception("database is locked"))
    monkeypatch.setattr("app.main.save_analysis", broken)
    r = client.post("/api/analyze", json=VPN)
    body = r.json()
    assert r.status_code == 200 and body["ok"]
    assert body["data"]["outcome"] in {"RECOMMEND", "CLARIFY", "ESCALATE"}
    assert "AUDIT_WRITE_FAILED" in body["data"]["reasons"]


@pytest.mark.parametrize("url,expected", [
    ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
    ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("sqlite:///x.db", "sqlite:///x.db"),
    ("", f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"),
])
def test_normalize_url(url, expected):
    assert normalize_url(url) == expected

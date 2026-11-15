"""API tests: envelope shape, request IDs, validation errors and search filters."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["ok"] and body["data"]["documents_indexed"] > 1000 and body["request_id"]


def test_analyze_returns_envelope():
    r = client.post("/api/analyze", json={"title": "Outlook not syncing",
                                          "description": "Outlook stuck on updating folder, webmail shows everything"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] and body["error"] is None
    assert body["data"]["outcome"] in {"RECOMMEND", "CLARIFY", "ESCALATE"}
    assert r.headers["X-Request-ID"] == body["request_id"]


def test_validation_error_uses_envelope():
    body = client.post("/api/analyze", json={"title": ""}).json()
    assert body["ok"] is False and body["error"]["code"] == "VALIDATION_ERROR"


def test_request_id_is_passed_through():
    r = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.json()["request_id"] == "abc-123"


def test_search_filters_by_application_and_date():
    body = client.post("/api/search", json={"query": "password expired",
                                            "filters": {"application": "Active Directory",
                                                        "date_from": "2026-01-01"}}).json()
    assert body["ok"] and body["data"]
    for hit in body["data"]:
        assert hit["metadata"]["application"] == "Active Directory"
        assert hit["metadata"]["created_at"][:10] >= "2026-01-01"


def test_draft_kb_articles_are_never_returned():
    body = client.post("/api/search", json={"query": "delete OST file outlook draft", "top_k": 50}).json()
    assert all(hit["source_id"] not in {"KB9001", "KB9002"} for hit in body["data"])

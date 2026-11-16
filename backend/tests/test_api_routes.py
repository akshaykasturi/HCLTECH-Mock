"""Tests for the UC4 FastAPI backend (app/main.py, app/uc4/api.py).

The real diagnosis pipeline (app/uc4/pipeline.py) does not exist yet. Tests marked MOCK PIPELINE
inject a fake diagnose() through FastAPI dependency overrides; its output is test data only and
is never produced by the application itself. "Pipeline unavailable" tests use the real lookup.

Every test uses its own temporary SQLite database. Fake secrets below are made up for these tests.
"""
import json
import logging
import sqlite3
import sys
import time
import types
from contextlib import closing
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import main as main_module
from app.main import create_app
from app.uc4 import api, audit, models
from app.uc4.api import ApiSettings, CaseSource, get_case_source, get_pipeline
from app.uc4.models import Case
from app.uc4.redact import find_leaks

FAKE_JWT = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJhcGktdGVzdCJ9.ZmFrZXNpZw"
FAKE_KEY = "nvp_live_ApiTestKey00000000000000000002"
FAKE_EMAIL = "api.reviewer@example.com"
FAKE_VALUES = (FAKE_JWT, FAKE_KEY, FAKE_EMAIL)
LABEL_KEYS = ("expected_class", "expected_cause", "expected_first_check", "expected_outcome", "difficulty",
              "culprit_dependency", "culprit_client", "requires_escalation", "generation", "worked_example")
ORIGIN = "http://127.0.0.1:5173"


def make_case(case_id="UC4-0050", route="GET /v1/orders/{id}", split="test", **extra) -> Case:
    data = {"case_id": case_id, "focal_correlation_id": f"c-{case_id.lower()}", "route": route,
            "onset_ts": "2026-10-15T05:17:22.435Z", "window_start": "2026-10-15T05:10:00Z",
            "window_end": "2026-10-15T05:25:00Z", "split": split, "difficulty": "hard",
            "expected_class": "timeout", "expected_cause": "upstream_dependency_slow",
            "summary": "504 on GET /v1/orders/{id}: upstream_dependency_slow (hard)"}
    data.update(extra)
    return Case.model_validate(data)


FAKE_CASES = {c.case_id: c for c in (make_case("UC4-0050"), make_case("UC4-0002", "POST /v1/payments", "train"))}


def make_diagnosis(case, diagnosis_id="dx-0001", outcome="RECOMMEND", **extra) -> dict:
    """MOCK PIPELINE output in the agreed Diagnosis shape (illustrative values, not a real diagnosis)."""
    report = None if outcome == "CLARIFY" else {
        "summary": "Likely a slow orders-db.",
        "causes": [{"cause_id": "upstream_dependency_slow", "explanation": "orders-db p95 rose sharply.",
                    "citations": [{"evidence_id": "metric:service:orders-db", "quote": "p95 2400 ms"}]}],
        "verification_steps": ["Open the orders-db latency dashboard for the same minutes."],
        "escalation": None,
    }
    diagnosis = {
        "diagnosis_id": diagnosis_id, "created_at": "2026-11-16T10:00:00.000Z", "case_id": case.case_id,
        "route": case.route, "onset_ts": "2026-10-15T05:17:22.435Z", "outcome": outcome,
        "failure_class": "timeout", "class_confidence": 0.82,
        "causes": [
            {"cause_id": "upstream_dependency_slow", "class": "timeout", "confidence": 0.71, "status": "probable",
             "supporting": ["metric:service:orders-db"], "contradicting": [], "missing_info": [],
             "first_check": "Check orders-db p95 latency.", "escalate": False, "escalate_reason": None,
             "near_tie": False},
            {"cause_id": "client_timeout_too_low", "class": "timeout", "confidence": 0.18, "status": "unsupported",
             "supporting": [], "contradicting": ["traffic:window"], "missing_info": [],
             "first_check": "Compare X-Client-Timeout-Ms with p95.", "escalate": False, "escalate_reason": None,
             "near_tie": False},
        ],
        "evidence": [{"id": "metric:service:orders-db", "kind": "metric",
                      "text": "orders-db p95 2400 ms vs 180 ms baseline", "data": {"p95_ms": 2400.0}},
                     {"id": "doc:timeouts-and-retries#2", "kind": "doc", "text": "Gateway timeout is 10000 ms.",
                      "data": {}}],
        "missing_info": [], "report": report,
        "report_findings": [{"code": "NUMBERS_OK", "severity": "info", "message": "All numbers match evidence."}],
        "generator": "template", "trace": [{"step": "evidence", "ms": 12.5, "detail": {}}],
    }
    diagnosis.update(extra)
    return diagnosis


class FakePipeline:
    """MOCK PIPELINE: records what it was given and returns test data."""

    def __init__(self, result=None, error=None, delay=0.0):
        self.result, self.error, self.delay, self.calls = result, error, delay, []

    def __call__(self, case):
        self.calls.append(case)
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result(case) if callable(self.result) else self.result


@pytest.fixture
def settings(tmp_path):
    return ApiSettings(audit_db_path=tmp_path / "audit_test.db", cors_origins=(ORIGIN,), diagnose_timeout_s=2.0)


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.dependency_overrides[get_case_source] = lambda: CaseSource(load_cases=lambda: FAKE_CASES,
                                                                         focal_status=lambda cid: 504)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def use_pipeline(app, pipeline):
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    return pipeline


def assert_envelope_ok(response, status=200):
    body = response.json()
    assert response.status_code == status, body
    assert set(body) == {"ok", "data", "error"} and body["ok"] is True and body["error"] is None
    return body["data"]


def assert_envelope_error(response, status, code):
    body = response.json()
    assert response.status_code == status, body
    assert set(body) == {"ok", "data", "error"} and body["ok"] is False and body["data"] is None
    assert set(body["error"]) == {"code", "message"} and body["error"]["code"] == code
    assert body["error"]["message"] and "Traceback" not in body["error"]["message"]
    return body["error"]


def diagnose_ok(client, app, case_id="UC4-0050", diagnosis_id="dx-0001", **extra):
    use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case, diagnosis_id, **extra)))
    return assert_envelope_ok(client.post("/api/diagnose", json={"case_id": case_id}), 201)


# ---------- A. startup ----------

def test_app_imports_and_starts_without_pipeline(client):
    assert main_module.app.title == "UC4 API failure diagnosis"
    fn, status = api.resolve_pipeline()
    assert fn is None and status == "pipeline module not available yet"  # real lookup, no pipeline.py
    data = assert_envelope_ok(client.get("/health"))
    assert data == {"api": "up", "database": "up", "pipeline": "not_ready",
                    "pipeline_detail": "pipeline module not available yet"}


def test_routes_are_registered(app):
    # Read from the OpenAPI schema: newer FastAPI versions keep included routers as one route entry.
    paths = {(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops}
    for expected in [("GET", "/health"), ("GET", "/health/ready"), ("GET", "/api/cases"),
                     ("POST", "/api/diagnose"), ("GET", "/api/diagnoses/{diagnosis_id}"),
                     ("POST", "/api/diagnoses/{diagnosis_id}/feedback"),
                     ("GET", "/api/diagnoses/{diagnosis_id}/feedback"), ("GET", "/api/audit/verify")]:
        assert expected in paths


def test_openapi_and_swagger_are_available(client):
    assert client.get("/docs").status_code == 200 and "swagger" in client.get("/docs").text.lower()
    spec = client.get("/openapi.json").json()
    assert {"/api/cases", "/api/diagnose", "/api/diagnoses/{diagnosis_id}",
            "/api/diagnoses/{diagnosis_id}/feedback", "/health"} <= set(spec["paths"])
    diagnose_doc = spec["paths"]["/api/diagnose"]["post"]
    assert {"404", "503", "504"} <= set(diagnose_doc["responses"])
    assert "DIAGNOSIS_NOT_READY" in json.dumps(diagnose_doc)
    assert "FeedbackRequest" in spec["components"]["schemas"]


def test_ready_endpoint(client):
    assert assert_envelope_ok(client.get("/health/ready"))["database"] == "up"


# ---------- B. cases ----------

def test_list_cases_fields_and_order(client):
    data = assert_envelope_ok(client.get("/api/cases"))
    assert [c["id"] for c in data] == ["UC4-0002", "UC4-0050"]  # sorted by id
    for item in data:
        assert set(item) == {"id", "route", "summary", "split"}
    assert data[1] == {"id": "UC4-0050", "route": "GET /v1/orders/{id}", "split": "test",
                       "summary": "HTTP 504 on GET /v1/orders/{id}, onset 2026-10-15 05:17 UTC"}


def test_case_summaries_never_contain_labels(client):
    text = json.dumps(client.get("/api/cases").json())
    for label in ("upstream_dependency_slow", "hard", "expected_", "timeout"):
        assert label not in text


def test_empty_case_list(client, app):
    app.dependency_overrides[get_case_source] = lambda: CaseSource(load_cases=dict, focal_status=lambda c: None)
    assert assert_envelope_ok(client.get("/api/cases")) == []


def test_invalid_case_records_are_skipped(client, app):
    bad = {"UC4-0001": {"case_id": "UC4-0001"}, "UC4-0050": FAKE_CASES["UC4-0050"]}
    app.dependency_overrides[get_case_source] = lambda: CaseSource(load_cases=lambda: bad, focal_status=lambda c: None)
    data = assert_envelope_ok(client.get("/api/cases"))
    assert [c["id"] for c in data] == ["UC4-0050"]
    assert data[0]["summary"].startswith("Failure on ")  # no status known: stated plainly


def test_case_loading_failure(client, app):
    def broken():
        raise OSError("disk read failed")
    app.dependency_overrides[get_case_source] = lambda: CaseSource(load_cases=broken)
    assert_envelope_error(client.get("/api/cases"), 503, "CASES_UNAVAILABLE")


def test_real_store_integration(settings):
    """Uses store.py and the real cases.jsonl / request logs (read-only)."""
    with TestClient(create_app(settings)) as real_client:
        data = assert_envelope_ok(real_client.get("/api/cases"))
    assert len(data) == 90 and data == sorted(data, key=lambda c: c["id"])
    by_id = {c["id"]: c for c in data}
    assert by_id["UC4-0050"]["summary"].startswith("HTTP 504 on ")
    assert {c["split"] for c in data} == {"train", "calibration", "test"}
    text = json.dumps(data)
    assert find_leaks(text) == []
    for label in ("token_expired", "upstream_dependency_slow", "(easy)", "(hard)", "insufficient"):
        assert label not in text


# ---------- C. diagnose ----------

def test_diagnose_with_mock_pipeline(client, app, settings):
    """MOCK PIPELINE: the API runs, checks, saves and returns the pipeline's Diagnosis."""
    pipeline = use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case)))
    data = assert_envelope_ok(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 201)
    assert data == make_diagnosis(FAKE_CASES["UC4-0050"])  # every field, evidence and citation kept
    assert audit.get_diagnosis(settings.audit_db_path, "dx-0001") == data
    given = pipeline.calls[0]
    assert given.case_id == "UC4-0050" and given.expected_cause is None and given.summary is None
    assert given.difficulty is None  # labels stripped before the pipeline sees the case


def test_diagnose_clarify_outcome_with_null_report(client, app):
    data = diagnose_ok(client, app, outcome="CLARIFY", missing_info=["dependency metrics"])
    assert data["outcome"] == "CLARIFY" and data["report"] is None


@pytest.mark.parametrize("body", [{}, {"case_id": ""}, {"case_id": "UC4 0050"}, {"case_id": "../etc"},
                                  {"case_id": 50}, {"case_id": "UC4-0050", "extra": 1}])
def test_diagnose_rejects_bad_requests(client, app, body):
    use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case)))
    error = assert_envelope_error(client.post("/api/diagnose", json=body), 422, "VALIDATION_ERROR")
    assert "case_id" in error["message"] or "extra" in error["message"]


def test_diagnose_unknown_case(client, app):
    pipeline = use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case)))
    assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-9999"}), 404, "CASE_NOT_FOUND")
    assert pipeline.calls == []


def test_diagnose_without_pipeline_returns_503(client, settings):
    """Real behaviour today: app/uc4/pipeline.py does not exist."""
    error = assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 503,
                                  "DIAGNOSIS_NOT_READY")
    assert error["message"] == "The diagnosis service is not ready yet."
    assert audit.list_events(settings.audit_db_path) == []  # nothing invented, nothing saved


def test_pipeline_failure(client, app, settings):
    use_pipeline(app, FakePipeline(error=RuntimeError(f"boom with {FAKE_KEY}")))
    error = assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 502,
                                  "DIAGNOSIS_FAILED")
    assert FAKE_KEY not in error["message"]
    assert audit.list_events(settings.audit_db_path) == []


def test_pipeline_timeout(client, app, settings):
    app.state.settings = ApiSettings(settings.audit_db_path, settings.cors_origins, diagnose_timeout_s=0.2)
    use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case), delay=1.0))
    assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 504, "DIAGNOSIS_TIMEOUT")
    time.sleep(1.0)  # let the abandoned worker finish: its result must still not be saved
    assert audit.list_events(settings.audit_db_path) == []


@pytest.mark.parametrize("broken", [
    lambda d: {k: v for k, v in d.items() if k != "causes"},          # missing field
    lambda d: {**d, "case_id": "UC4-0002"},                            # wrong case
    lambda d: {**d, "outcome": "MAYBE"},                               # bad outcome
    lambda d: {**d, "outcome": "CLARIFY"},                             # CLARIFY with a report
    lambda d: {**d, "evidence": "not a list"},
    lambda d: {**d, "diagnosis_id": "bad id"},
    lambda d: "not a diagnosis",
])
def test_diagnosis_contract_is_enforced(client, app, settings, broken):
    use_pipeline(app, FakePipeline(lambda case: broken(make_diagnosis(case))))
    assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 502, "DIAGNOSIS_INVALID")
    assert audit.list_events(settings.audit_db_path) == []


def test_diagnosis_model_is_used_when_it_exists(client, app, monkeypatch):
    """When the pipeline team adds models.Diagnosis, results are validated with it (stand-in here)."""
    class Diagnosis(BaseModel):  # stand-in for the future models.Diagnosis
        diagnosis_id: str
        case_id: str
        class_confidence: float

    monkeypatch.setattr(models, "Diagnosis", Diagnosis, raising=False)
    use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case, class_confidence="very")))
    assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 502, "DIAGNOSIS_INVALID")


def test_pipeline_returning_a_pydantic_model(client, app):
    class Result(BaseModel):
        model_config = {"extra": "allow"}

    use_pipeline(app, FakePipeline(lambda case: Result(**make_diagnosis(case))))
    data = assert_envelope_ok(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 201)
    assert data["causes"][0]["supporting"] == ["metric:service:orders-db"]


def test_duplicate_diagnosis_id(client, app, settings):
    diagnose_ok(client, app)
    assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 409, "DIAGNOSIS_CONFLICT")
    assert len(audit.list_events(settings.audit_db_path)) == 1


def test_persistence_failure_is_not_reported_as_success(app, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the database folder should be")
    bad = ApiSettings(audit_db_path=blocker / "audit.db", cors_origins=(ORIGIN,), diagnose_timeout_s=2.0)
    app.state.settings = bad
    with TestClient(app) as bad_client:
        use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case)))
        assert_envelope_error(bad_client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 503,
                              "DATABASE_UNAVAILABLE")
        assert_envelope_error(bad_client.get("/api/diagnoses/dx-0001"), 503, "DATABASE_UNAVAILABLE")
        assert_envelope_error(bad_client.post("/api/diagnoses/dx-0001/feedback", json={"verdict": "confirm"}),
                              503, "DATABASE_UNAVAILABLE")
        assert_envelope_error(bad_client.get("/api/audit/verify"), 503, "DATABASE_UNAVAILABLE")
        health = assert_envelope_ok(bad_client.get("/health"))
        assert health["database"] == "down" and health["api"] == "up"
        assert_envelope_error(bad_client.get("/health/ready"), 503, "DATABASE_UNAVAILABLE")
        assert assert_envelope_ok(bad_client.get("/api/cases"))  # cases still served


def test_corrupt_database_file(app, tmp_path):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not sqlite" * 200)
    app.state.settings = ApiSettings(audit_db_path=corrupt, cors_origins=(ORIGIN,), diagnose_timeout_s=2.0)
    with TestClient(app) as c:
        assert_envelope_error(c.get("/api/diagnoses/dx-0001"), 503, "DATABASE_UNAVAILABLE")


# ---------- D. retrieval ----------

def test_get_saved_diagnosis(client, app):
    saved = diagnose_ok(client, app)
    again = assert_envelope_ok(client.get("/api/diagnoses/dx-0001"))
    assert again == saved
    assert set(again) == set(api.DIAGNOSIS_FIELDS)
    assert again["report"]["causes"][0]["citations"] == [{"evidence_id": "metric:service:orders-db",
                                                          "quote": "p95 2400 ms"}]


def test_get_missing_diagnosis(client):
    error = assert_envelope_error(client.get("/api/diagnoses/dx-missing"), 404, "DIAGNOSIS_NOT_FOUND")
    assert error["message"] == "The requested diagnosis was not found."


@pytest.mark.parametrize("bad_id", ["bad id", "-starts-with-dash", "x" * 101])
def test_get_invalid_diagnosis_id(client, bad_id):
    assert_envelope_error(client.get(f"/api/diagnoses/{bad_id}"), 422, "VALIDATION_ERROR")


def test_retrieval_does_not_rerun_pipeline(client, app):
    diagnose_ok(client, app)
    pipeline = use_pipeline(app, FakePipeline(error=AssertionError("must not be called")))
    assert_envelope_ok(client.get("/api/diagnoses/dx-0001"))
    assert pipeline.calls == []


# ---------- E. feedback ----------

@pytest.mark.parametrize("payload", [
    {"verdict": "confirm", "cause_id": "upstream_dependency_slow"},
    {"verdict": "reject", "cause_id": "client_timeout_too_low", "note": "Timeouts were configured correctly."},
    {"verdict": "annotate", "note": "Re-check after the next deploy."},
])
def test_valid_feedback(client, app, payload):
    diagnose_ok(client, app)
    data = assert_envelope_ok(client.post("/api/diagnoses/dx-0001/feedback", json=payload), 201)
    assert data["verdict"] == payload["verdict"] and data["diagnosis_id"] == "dx-0001"
    assert data["cause_id"] == payload.get("cause_id") and data["note"] == payload.get("note")
    assert data["case_id"] == "UC4-0050" and data["created_at"].endswith("Z") and data["feedback_id"]


@pytest.mark.parametrize("payload", [
    {"verdict": "approve"}, {"verdict": "CONFIRM"}, {}, {"verdict": "annotate"},
    {"verdict": "annotate", "note": "   "}, {"verdict": "confirm", "note": "x" * (api.MAX_NOTE_CHARS + 1)},
    {"verdict": "confirm", "cause_id": "bad cause id"}, {"verdict": "confirm", "unexpected": True},
    {"verdict": "confirm", "note": 12},
])
def test_invalid_feedback_is_rejected(client, app, settings, payload):
    diagnose_ok(client, app)
    assert_envelope_error(client.post("/api/diagnoses/dx-0001/feedback", json=payload), 422, "VALIDATION_ERROR")
    assert audit.get_feedback(settings.audit_db_path, "dx-0001") == []


def test_feedback_for_missing_diagnosis(client):
    assert_envelope_error(client.post("/api/diagnoses/dx-missing/feedback", json={"verdict": "confirm"}),
                          404, "DIAGNOSIS_NOT_FOUND")
    assert_envelope_error(client.get("/api/diagnoses/dx-missing/feedback"), 404, "DIAGNOSIS_NOT_FOUND")


def test_feedback_unknown_cause(client, app):
    diagnose_ok(client, app)
    assert_envelope_error(client.post("/api/diagnoses/dx-0001/feedback",
                                      json={"verdict": "confirm", "cause_id": "dns_failure"}), 422, "UNKNOWN_CAUSE")


def test_feedback_is_append_only(client, app, settings):
    saved = diagnose_ok(client, app)
    verdicts = ["reject", "annotate", "confirm"]
    for verdict in verdicts:
        payload = {"verdict": verdict, "note": f"review {verdict}"}
        assert_envelope_ok(client.post("/api/diagnoses/dx-0001/feedback", json=payload), 201)
    history = assert_envelope_ok(client.get("/api/diagnoses/dx-0001/feedback"))
    assert [f["verdict"] for f in history] == verdicts and len({f["feedback_id"] for f in history}) == 3
    assert assert_envelope_ok(client.get("/api/diagnoses/dx-0001")) == saved  # diagnosis unchanged
    assert audit.verify_chain(settings.audit_db_path)["valid"]
    chain = assert_envelope_ok(client.get("/api/audit/verify"))
    assert chain["valid"] is True and chain["events_checked"] == 4


def test_secrets_in_notes_are_masked(client, app, settings, caplog):
    diagnose_ok(client, app)
    note = f"Customer {FAKE_EMAIL} pasted Bearer {FAKE_JWT} and key {FAKE_KEY}"
    with caplog.at_level(logging.DEBUG):
        data = assert_envelope_ok(client.post("/api/diagnoses/dx-0001/feedback",
                                              json={"verdict": "annotate", "note": note}), 201)
    stored = audit.get_feedback(settings.audit_db_path, "dx-0001")[0]["note"]
    for text in (data["note"], stored, settings.audit_db_path.read_bytes().decode("latin-1"), caplog.text):
        assert not any(v in text for v in FAKE_VALUES)
        assert find_leaks(text) == []
    assert "<EMAIL>" in data["note"] or "<email>" in data["note"]


# ---------- F. response contract ----------

def test_unknown_route_and_method_use_the_envelope(client):
    assert_envelope_error(client.get("/api/nope"), 404, "NOT_FOUND")
    assert_envelope_error(client.delete("/api/cases"), 405, "METHOD_NOT_ALLOWED")


def test_malformed_json_body(client):
    response = client.post("/api/diagnose", content=b"{not json", headers={"Content-Type": "application/json"})
    assert_envelope_error(response, 422, "VALIDATION_ERROR")


def test_validation_errors_do_not_echo_input(client):
    response = client.post("/api/diagnose", json={"case_id": FAKE_KEY + " !"})
    error = assert_envelope_error(response, 422, "VALIDATION_ERROR")
    assert FAKE_KEY not in error["message"]


def test_unexpected_exception_hides_details(client, app):
    def explode():
        raise ZeroDivisionError(f"secret detail {FAKE_KEY}")
    app.dependency_overrides[get_case_source] = explode  # an unexpected bug inside the app
    response = client.get("/api/cases")
    error = assert_envelope_error(response, 500, "INTERNAL_ERROR")
    assert FAKE_KEY not in json.dumps(response.json()) and "ZeroDivision" not in error["message"]


# ---------- G. security ----------

def test_secrets_in_pipeline_output_are_masked(client, app, settings, caplog):
    """MOCK PIPELINE output that (wrongly) contains secrets: they are masked before saving and returning."""
    dirty = dict(evidence=[{"id": "request:c-1", "kind": "request", "text": f"key {FAKE_KEY} from {FAKE_EMAIL}",
                            "data": {"request_headers": {"Authorization": f"Bearer {FAKE_JWT}", "X-Api-Key": FAKE_KEY}}}])
    with caplog.at_level(logging.DEBUG):
        data = diagnose_ok(client, app, **dirty)
        fetched = client.get("/api/diagnoses/dx-0001").json()
    for text in (json.dumps(data), json.dumps(fetched), settings.audit_db_path.read_bytes().decode("latin-1"),
                 caplog.text):
        assert not any(v in text for v in FAKE_VALUES)
        assert find_leaks(text) == []
    assert data["evidence"][0]["data"]["request_headers"] == {"Authorization": "<redacted>", "X-Api-Key": "<redacted>"}


def test_logs_have_request_ids_and_no_secrets(client, caplog):
    with caplog.at_level(logging.INFO):
        response = client.post("/api/diagnose", json={"case_id": "UC4-0050"},
                               headers={"Authorization": f"Bearer {FAKE_JWT}", "X-Api-Key": FAKE_KEY})
    request_id = response.headers["X-Request-ID"]
    assert any(request_id in r.getMessage() and "/api/diagnose" in r.getMessage() and "503" in r.getMessage()
               and "DIAGNOSIS_NOT_READY" in r.getMessage() for r in caplog.records)
    assert all(getattr(r, "request_id", None) is not None for r in caplog.records)
    assert not any(v in caplog.text for v in FAKE_VALUES)


# ---------- H. integration ----------

def test_request_id_propagation(client, app, settings):
    good = client.get("/health", headers={"X-Request-ID": "frontend-req-0001"})
    assert good.headers["X-Request-ID"] == "frontend-req-0001"
    bad = client.get("/health", headers={"X-Request-ID": "bad id <script>"})
    assert bad.headers["X-Request-ID"] != "bad id <script>" and len(bad.headers["X-Request-ID"]) == 32
    use_pipeline(app, FakePipeline(lambda case: make_diagnosis(case)))
    response = client.post("/api/diagnose", json={"case_id": "UC4-0050"}, headers={"X-Request-ID": "req-diag-0001"})
    assert response.status_code == 201
    event = audit.list_events(settings.audit_db_path)[0]
    assert event["request_id"] == "req-diag-0001"  # passed into the audit log
    fb = client.post("/api/diagnoses/dx-0001/feedback", json={"verdict": "confirm"},
                     headers={"X-Request-ID": "req-fb-0001"})
    assert fb.json()["data"]["request_id"] == "req-fb-0001"


def test_cors(client):
    allowed = client.options("/api/cases", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"})
    assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == ORIGIN
    simple = client.get("/api/cases", headers={"Origin": ORIGIN})
    assert simple.headers["access-control-allow-origin"] == ORIGIN
    assert "x-request-id" in simple.headers["access-control-expose-headers"].lower()
    other = client.get("/api/cases", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_settings_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("UC4_AUDIT_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("UC4_CORS_ORIGINS", "http://127.0.0.1:3000, http://127.0.0.1:5173")
    monkeypatch.setenv("UC4_DIAGNOSE_TIMEOUT_S", "15")
    s = api.load_api_settings()
    assert s.audit_db_path == tmp_path / "x.db" and s.diagnose_timeout_s == 15.0
    assert s.cors_origins == ("http://127.0.0.1:3000", "http://127.0.0.1:5173")
    for name, value in (("UC4_CORS_ORIGINS", "*"), ("UC4_DIAGNOSE_TIMEOUT_S", "abc"), ("UC4_DIAGNOSE_TIMEOUT_S", "0")):
        monkeypatch.setenv("UC4_CORS_ORIGINS", "http://127.0.0.1:5173")
        monkeypatch.setenv("UC4_DIAGNOSE_TIMEOUT_S", "15")
        monkeypatch.setenv(name, value)
        with pytest.raises(ValueError):
            api.load_api_settings()


def test_default_database_path_is_git_ignored(monkeypatch):
    monkeypatch.delenv("UC4_AUDIT_DB", raising=False)
    path = api.load_api_settings().audit_db_path
    assert path.suffix == ".db" and path.parts[-3:-1] == ("data", "audit")
    assert "app" not in path.parts  # not inside the source-code folder
    gitignore = (api.BACKEND_DIR.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.db" in gitignore


@pytest.mark.parametrize("source,expected_status", [
    ("def diagnose(case):\n    return case\n", "ready"),
    ("def diagnose(case_id):\n    return case_id\n", "ready"),
    ("def diagnose(case, options=None):\n    return case\n", "ready"),
    ("def diagnose(a, b):\n    return a\n", "diagnose() signature is not the agreed diagnose(case) or diagnose(case_id)"),
    ("diagnose = 3\n", "pipeline has no diagnose() function"),
    ("import a_module_that_does_not_exist\n", "pipeline cannot be imported (missing module a_module_that_does_not_exist)"),
])
def test_pipeline_lookup(monkeypatch, tmp_path, source, expected_status):
    """The real resolver, pointed at temporary pipeline modules (none of these is the real pipeline)."""
    pkg_dir = tmp_path / "fakepkg"
    pkg_dir.mkdir()
    (pkg_dir / "pipeline.py").write_text(source, encoding="utf-8")
    monkeypatch.delitem(sys.modules, "app.uc4.pipeline", raising=False)
    import app.uc4 as uc4_pkg
    monkeypatch.setattr(uc4_pkg, "__path__", list(uc4_pkg.__path__) + [str(pkg_dir)])
    try:
        fn, status = api.resolve_pipeline()
        assert status == expected_status
        if fn is not None:
            assert fn(FAKE_CASES["UC4-0050"]) in (FAKE_CASES["UC4-0050"], "UC4-0050")
    finally:
        sys.modules.pop("app.uc4.pipeline", None)


def test_real_pipeline_module_is_absent_in_this_branch():
    """Guards the 503 tests: they describe today's repository, where pipeline.py is not committed."""
    import importlib.util
    assert importlib.util.find_spec("app.uc4.pipeline") is None


def test_audit_db_initialised_on_startup(settings):
    assert not settings.audit_db_path.exists()
    with TestClient(create_app(settings)):
        pass
    with closing(sqlite3.connect(str(settings.audit_db_path))) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"audit_events", "audit_meta"} <= tables


def test_docs_loader_is_not_called_per_request(client, monkeypatch):
    from app.uc4 import docs_loader
    calls = []
    monkeypatch.setattr(docs_loader, "ingest", lambda *a, **k: calls.append(1))
    client.get("/api/cases")
    client.get("/health")
    assert calls == []

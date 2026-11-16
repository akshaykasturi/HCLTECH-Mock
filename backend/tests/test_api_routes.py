"""Tests for the UC4 FastAPI backend (app/main.py, app/uc4/api.py).

Two kinds of diagnose tests:
- REAL PIPELINE (section I): the team's app.uc4.diagnose.diagnose on real cases from the dataset.
- MOCK PIPELINE: a fake diagnose() injected through FastAPI dependency overrides, to test error paths
  and contract checks. Its output is test data in the models.Diagnosis shape, never produced by the app.

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

from app import main as main_module
from app.main import create_app
from app.uc4 import api, audit
from app.uc4 import diagnose as diagnose_module
from app.uc4.api import ApiSettings, CaseSource, get_case_source, get_pipeline
from app.uc4.models import Case, Diagnosis
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
    """MOCK PIPELINE output in the final models.Diagnosis shape (illustrative values, not a real diagnosis).

    On CLARIFY no cause is claimed (ranked empty, failure_class None), as the real pipeline does.
    """
    claim = outcome == "RECOMMEND"
    ranked = [
        {"rank": 1, "cause": "upstream_dependency_slow", "failure_class": "timeout", "confidence": 0.71,
         "status": "probable", "near_tie": False,
         "supporting": [{"signal": "dependency_latency_spike", "present": True, "ratio": 6.2,
                         "evidence_ids": ["metric:service:orders-db"]}],
         "contradicting": [], "confirming_seen": ["dependency_latency_spike"], "confirming_missing": [],
         "first_check": "Check orders-db p95 latency.", "escalate": False, "missing_info": []},
        {"rank": 2, "cause": "client_timeout_too_low", "failure_class": "timeout", "confidence": 0.18,
         "status": "unsupported", "near_tie": False, "supporting": [],
         "contradicting": [{"signal": "client_timeout_header_low", "present": False, "ratio": 0.2,
                            "evidence_ids": ["traffic:window"]}],
         "first_check": "Compare X-Client-Timeout-Ms with p95.", "escalate": False},
    ] if claim else []
    report = {
        "case_id": case.case_id, "outcome": outcome,
        "summary": "Likely a slow orders-db." if claim else "More information is needed.",
        "causes": [{"cause": "upstream_dependency_slow", "likelihood": "probable",
                    "explanation": "orders-db p95 rose sharply.",
                    "supporting": [{"evidence_id": "metric:service:orders-db", "quote": "p95 2400 ms"}]}]
        if claim else [],
        "verification_steps": [{"action": "Open the orders-db latency dashboard for the same minutes.",
                                "why": "Shows whether the spike matches the onset.",
                                "cites": ["metric:service:orders-db"]}] if claim else [],
        "escalation": {"needed": False}, "missing_info": [] if claim else ["dependency metrics"],
    }
    diagnosis = {
        "diagnosis_id": diagnosis_id, "created_at": "2026-11-16T10:00:00Z", "case_id": case.case_id,
        "route": case.route, "onset_ts": "2026-10-15T05:17:22.435000Z", "outcome": outcome, "escalate": False,
        "failure_class": "timeout" if claim else None, "class_confidence": 0.89 if claim else None,
        "ranked": ranked, "alternatives": [], "tell_apart": None,
        "evidence": [{"id": "metric:service:orders-db", "kind": "metric",
                      "text": "orders-db p95 2400 ms vs 180 ms baseline", "data": {"p95_ms": 2400.0}},
                     {"id": "traffic:window", "kind": "traffic", "text": "120 requests in the window",
                      "data": {"requests": 120}}],
        "missing_info": [] if claim else ["dependency metrics"], "report": report,
        "report_findings": [{"code": "NUMBERS_OK", "severity": "info", "message": "All numbers match evidence.",
                             "where": "summary"}],
        "groundedness": 1.0, "generator": "template",
        "trace": [{"step": "collect_evidence", "ms": 12.5, "detail": "2 items, 0 missing"}],
    }
    diagnosis.update(extra)
    return diagnosis


def as_json(diagnosis) -> dict:
    """What the API returns for a valid Diagnosis: models.Diagnosis dumped with mode="json"."""
    return Diagnosis.model_validate(diagnosis).model_dump(mode="json")


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

def test_app_starts_with_the_real_pipeline(client):
    assert main_module.app.title == "UC4 API failure diagnosis"
    fn, status = api.resolve_pipeline()
    assert fn is diagnose_module.diagnose and status == "ready"  # app.uc4.diagnose, not the old pipeline.py
    data = assert_envelope_ok(client.get("/health"))
    assert data == {"api": "up", "database": "up", "pipeline": "ready", "pipeline_detail": "ready"}


def test_broken_pipeline_import_is_reported_not_fatal(client, monkeypatch, settings):
    """If app.uc4.diagnose cannot be imported, /health says not_ready and /api/diagnose answers 503."""
    monkeypatch.setitem(sys.modules, "app.uc4.diagnose", None)  # makes the import fail
    fn, status = api.resolve_pipeline()
    assert fn is None and status.startswith("pipeline cannot be imported")
    health = assert_envelope_ok(client.get("/health"))
    assert health["pipeline"] == "not_ready" and health["api"] == "up"
    error = assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 503,
                                  "DIAGNOSIS_NOT_READY")
    assert error["message"] == "The diagnosis service is not ready yet."
    assert audit.list_events(settings.audit_db_path) == []  # nothing invented, nothing saved


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
    assert data == as_json(make_diagnosis(FAKE_CASES["UC4-0050"]))  # every field, evidence and citation kept
    assert audit.get_diagnosis(settings.audit_db_path, "dx-0001") == data
    given = pipeline.calls[0]
    assert given.case_id == "UC4-0050" and given.expected_cause is None and given.summary is None
    assert given.difficulty is None  # labels stripped before the pipeline sees the case


def test_diagnose_clarify_outcome_claims_no_cause(client, app):
    data = diagnose_ok(client, app, outcome="CLARIFY")
    assert data["outcome"] == "CLARIFY" and data["ranked"] == [] and data["failure_class"] is None
    assert data["escalate"] is False and data["missing_info"] == ["dependency metrics"]


def test_diagnose_report_may_be_null(client, app):
    data = diagnose_ok(client, app, outcome="CLARIFY", report=None)
    assert data["report"] is None


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


def test_diagnose_without_pipeline_returns_503(client, app, settings):
    use_pipeline(app, None)  # get_pipeline found nothing
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


def _ranked_with(d, **change):
    return {**d, "ranked": [{**d["ranked"][0], **change}, *d["ranked"][1:]]}


@pytest.mark.parametrize("broken", [
    lambda d: {k: v for k, v in d.items() if k != "outcome"},         # missing required field
    lambda d: {k: v for k, v in d.items() if k != "escalate"},        # escalate flag is required
    lambda d: {**d, "case_id": "UC4-0002"},                            # wrong case
    lambda d: {**d, "outcome": "MAYBE"},                               # bad outcome
    lambda d: {**d, "outcome": "ESCALATE"},                            # escalation is a flag, not an outcome
    lambda d: {**d, "outcome": "CLARIFY"},                             # CLARIFY that still claims causes
    lambda d: {**d, "class_confidence": "very"},                       # wrong type
    lambda d: _ranked_with(d, status="confirmed"),                     # causes are never "confirmed"
    lambda d: _ranked_with(d, cause="client_timeout_too_low"),         # duplicate cause names
    lambda d: _ranked_with(d, cause="bad cause name"),                 # unusable as a feedback cause_id
    lambda d: {**d, "evidence": "not a list"},
    lambda d: {**d, "diagnosis_id": "bad id"},
    lambda d: "not a diagnosis",
])
def test_diagnosis_contract_is_enforced(client, app, settings, broken):
    use_pipeline(app, FakePipeline(lambda case: broken(make_diagnosis(case))))
    assert_envelope_error(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 502, "DIAGNOSIS_INVALID")
    assert audit.list_events(settings.audit_db_path) == []


def test_pipeline_returning_a_diagnosis_model(client, app):
    """The real pipeline returns a models.Diagnosis object; the API dumps it with mode="json"."""
    model = Diagnosis.model_validate(make_diagnosis(FAKE_CASES["UC4-0050"]))
    use_pipeline(app, FakePipeline(lambda case: model))
    data = assert_envelope_ok(client.post("/api/diagnose", json={"case_id": "UC4-0050"}), 201)
    assert data == model.model_dump(mode="json")
    assert data["ranked"][0]["supporting"][0]["evidence_ids"] == ["metric:service:orders-db"]


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
    assert set(again) == set(api.DIAGNOSIS_FIELDS) == set(Diagnosis.model_fields)
    assert again["report"]["causes"][0]["supporting"] == [{"evidence_id": "metric:service:orders-db",
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
    # Masked with redact.mask_text (same markers as redact.py).
    assert data["note"] == "Customer <EMAIL> pasted Bearer <TOKEN> and key nvp_live_<KEY>"


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


def test_logs_have_request_ids_and_no_secrets(client, app, caplog):
    use_pipeline(app, None)  # an error path, so the log line carries an error code
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


def test_pipeline_lookup_uses_app_uc4_diagnose(monkeypatch):
    """The resolver returns app.uc4.diagnose.diagnose itself (no adapter), and never the old pipeline.py."""
    monkeypatch.setitem(sys.modules, "app.uc4.pipeline", None)  # the old module must not matter
    fn, status = api.resolve_pipeline()
    assert status == "ready" and fn is diagnose_module.diagnose


def test_pipeline_without_diagnose_function(monkeypatch):
    monkeypatch.setitem(sys.modules, "app.uc4.diagnose", types.SimpleNamespace(diagnose=3))
    fn, status = api.resolve_pipeline()
    assert fn is None and status == "app.uc4.diagnose has no diagnose() function"


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


# ---------- I. REAL PIPELINE (app.uc4.diagnose.diagnose on real cases, no overrides) ----------
# Case ids chosen by running the real pipeline: UC4-0001 RECOMMEND, UC4-0019 RECOMMEND + escalate,
# UC4-0085 CLARIFY. The assertions check the contract, not which cause wins (that is the pipeline's job).

@pytest.fixture
def real_client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def real_diagnose(real_client, case_id):
    return assert_envelope_ok(real_client.post("/api/diagnose", json={"case_id": case_id}), 201)


def test_real_diagnosis_recommend(real_client, settings):
    data = real_diagnose(real_client, "UC4-0001")
    assert set(data) == set(Diagnosis.model_fields)
    assert data["case_id"] == "UC4-0001" and data["outcome"] == "RECOMMEND" and data["escalate"] is False
    ranked = data["ranked"]
    assert ranked and [c["rank"] for c in ranked] == list(range(1, len(ranked) + 1))
    assert data["failure_class"] == ranked[0]["failure_class"]
    assert all(c["status"] in ("likely", "probable", "unsupported") for c in ranked)  # never "confirmed"
    assert 0 <= data["class_confidence"] <= 1 and all(0 <= c["confidence"] <= 1 for c in ranked)
    assert audit.get_diagnosis(settings.audit_db_path, data["diagnosis_id"]) == data  # saved as returned


def test_real_diagnosis_escalate_flag(real_client):
    data = real_diagnose(real_client, "UC4-0019")
    assert data["outcome"] == "RECOMMEND" and data["escalate"] is True  # a flag, not an ESCALATE outcome
    assert data["ranked"]


def test_real_diagnosis_clarify(real_client):
    data = real_diagnose(real_client, "UC4-0085")
    assert data["outcome"] == "CLARIFY" and data["escalate"] is False
    assert data["ranked"] == [] and data["failure_class"] is None and data["class_confidence"] is None
    assert data["missing_info"]  # says what is missing instead of guessing


def test_real_diagnosis_unknown_case_is_404(real_client, settings):
    assert_envelope_error(real_client.post("/api/diagnose", json={"case_id": "UC4-9999"}), 404, "CASE_NOT_FOUND")
    assert audit.list_events(settings.audit_db_path) == []


def test_real_pipeline_never_sees_labels(app, settings):
    """The real diagnose() runs, but on a copy of the case without evaluation labels."""
    seen = []

    def spy(case):
        seen.append(case)
        return diagnose_module.diagnose(case)

    app.dependency_overrides.pop(get_case_source)  # real cases from the dataset
    use_pipeline(app, spy)
    with TestClient(app) as c:
        data = real_diagnose(c, "UC4-0001")
    assert data["outcome"] == "RECOMMEND"
    assert all(getattr(seen[0], name) in (None, []) for name in api.LABEL_FIELDS)


def test_real_diagnosis_json_serialization(real_client):
    data = real_diagnose(real_client, "UC4-0001")
    assert as_json(data) == data  # round-trips through models.Diagnosis unchanged
    assert datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")).tzinfo is not None
    assert isinstance(json.loads(json.dumps(data)), dict)


def test_real_diagnosis_output_has_no_secrets_or_labels(real_client):
    data = real_diagnose(real_client, "UC4-0019")
    text = json.dumps(data)
    assert find_leaks(text) == []
    for key in ("expected_cause", "expected_class", "expected_outcome", "requires_escalation", "difficulty"):
        assert f'"{key}"' not in text


def test_real_feedback_by_ranked_cause(real_client, settings):
    data = real_diagnose(real_client, "UC4-0001")
    url = f"/api/diagnoses/{data['diagnosis_id']}/feedback"
    second = data["ranked"][1]["cause"]  # any ranked cause can be reviewed, not only the top one
    fb = assert_envelope_ok(real_client.post(url, json={"verdict": "reject", "cause_id": second}), 201)
    assert fb["cause_id"] == second
    assert_envelope_error(real_client.post(url, json={"verdict": "confirm", "cause_id": "not_a_ranked_cause"}),
                          422, "UNKNOWN_CAUSE")
    whole = assert_envelope_ok(real_client.post(url, json={"verdict": "confirm"}), 201)  # whole diagnosis
    assert whole["cause_id"] is None
    history = assert_envelope_ok(real_client.get(url))
    assert [(f["verdict"], f["cause_id"]) for f in history] == [("reject", second), ("confirm", None)]
    assert assert_envelope_ok(real_client.get("/api/audit/verify"))["valid"] is True


def test_real_feedback_on_clarify_allows_only_whole_diagnosis(real_client):
    data = real_diagnose(real_client, "UC4-0085")
    url = f"/api/diagnoses/{data['diagnosis_id']}/feedback"
    assert_envelope_error(real_client.post(url, json={"verdict": "confirm", "cause_id": "token_expired"}),
                          422, "UNKNOWN_CAUSE")  # CLARIFY claims no cause
    note = "Asked the on-call team for the missing metrics."
    fb = assert_envelope_ok(real_client.post(url, json={"verdict": "annotate", "note": note}), 201)
    assert fb["cause_id"] is None and fb["note"] == note

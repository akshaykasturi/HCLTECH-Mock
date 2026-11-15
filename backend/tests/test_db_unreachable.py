"""The app keeps working when the database can't be reached: startup doesn't hang or crash,
/health says so, analyses still return (flagged AUDIT_WRITE_FAILED), history/stats give 503."""
import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.session import connect_args, reset_db_state
from app.main import app

# nothing listens on port 1, so the connection is refused straight away
UNREACHABLE = "postgresql://u:secretpw@127.0.0.1:1/db"


@pytest.fixture
def unreachable_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_S", "3")
    get_settings.cache_clear()
    reset_db_state()
    yield
    reset_db_state()  # the next database use rebuilds the engine from the restored test settings
    get_settings.cache_clear()


def test_postgres_gets_connect_timeout(monkeypatch):
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_S", "7")
    get_settings.cache_clear()
    try:
        assert connect_args("postgresql+psycopg://u:p@h/db") == {"connect_timeout": 7}
        assert connect_args("sqlite:///x.db") == {"check_same_thread": False}
    finally:
        get_settings.cache_clear()


def test_app_degrades_when_database_unreachable(unreachable_db, caplog):
    caplog.set_level(logging.INFO, logger="ticket-assistant")
    start = time.perf_counter()
    with TestClient(app) as client:  # `with` runs the lifespan, i.e. real startup
        assert time.perf_counter() - start < 30, "startup must fail fast, not hang"

        health = client.get("/health").json()
        assert health["ok"] is True
        assert health["data"]["database"] == "unavailable"
        assert health["data"]["database_dialect"] == "postgresql"

        r = client.post("/api/analyze", json={"title": "VPN keeps disconnecting",
                                              "description": "VPN drops every 10 minutes when working from home."})
        body = r.json()
        assert r.status_code == 200 and body["ok"] is True
        assert body["data"]["outcome"] in {"RECOMMEND", "CLARIFY", "ESCALATE"}
        assert "AUDIT_WRITE_FAILED" in body["data"]["reasons"]

        for method, path, payload in [("get", "/api/stats", None), ("get", "/api/analyses", None),
                                      ("get", "/api/analyses/some-id", None),
                                      ("post", "/api/analyses/some-id/feedback",
                                       {"verdict": "useful", "target": "recommendation"})]:
            r = getattr(client, method)(path, json=payload) if payload else getattr(client, method)(path)
            body = r.json()
            assert r.status_code == 503, path
            assert body["ok"] is False and body["error"]["code"] == "DATABASE_UNAVAILABLE", path
            assert body["error"]["retryable"] is True
            assert body["request_id"]

    logged = caplog.text
    assert "database unavailable at startup (postgresql)" in logged
    assert "secretpw" not in logged and "u:secretpw@" not in logged  # the URL is never logged

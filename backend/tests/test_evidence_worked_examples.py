"""Evidence for the worked examples shows what an engineer needs to see."""
import re

import pytest

from app.uc4.evidence import collect_evidence
from app.uc4.store import get_case


def _by_id(case_id: str) -> dict:
    return {item.id: item for item in collect_evidence(get_case(case_id))}


def test_uc4_0050_shows_504_from_orders_db_and_p95_jump() -> None:
    items = _by_id("UC4-0050")

    request = items["request:c-1e93f5b875"]
    assert request.data["status"] == 504
    assert request.data["upstream_service"] == "orders-db"
    assert "504" in request.text and "orders-db" in request.text

    dep = items["metric:service:orders-db"]
    assert dep.data["p95_ms"]["ratio"] >= 3, dep.text  # big p95 increase vs the hour before
    assert "orders-db" in dep.text


def test_uc4_0038_shows_dominant_client_and_rate_limit_headers() -> None:
    items = _by_id("UC4-0038")

    sample = items["traffic:window"].data["window"]
    assert sample["top_client_share"] >= 0.5  # one client sends most of the logged requests
    assert sample["top_client"] == items["request:c-8f4e3a51a3"].data["client_id"]

    # The traffic increase comes from metrics (all traffic), not from log counts.
    rps = items["metric:endpoint:GET /v1/inventory/{sku}"].data["rps"]
    assert rps["ratio"] == pytest.approx(2.56, abs=0.1)

    headers = items["request:c-8f4e3a51a3"].data["rate_limit_headers"]
    assert headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in headers
    assert "X-RateLimit-Remaining 0" in items["request:c-8f4e3a51a3"].text


def test_uc4_0050_does_not_claim_a_traffic_increase() -> None:
    # Logs are a sample: more log lines in the window must not read as more traffic.
    items = _by_id("UC4-0050")

    rps = items["metric:endpoint:GET /v1/orders/{id}"].data["rps"]
    assert 0.8 <= rps["ratio"] <= 1.25  # metrics say volume is flat

    traffic = items["traffic:window"]
    assert traffic.text.startswith("Logged requests (sample")
    assert not re.search(r"/min|\brps\b|requests per", traffic.text)
    assert "requests_per_min" not in traffic.data["window"]
    assert "logged_requests" not in traffic.data["baseline"]  # no count comparison with the baseline


def test_log_sample_never_reports_rates_or_baseline_counts() -> None:
    from app.uc4.store import load_cases
    for case in load_cases().values():
        traffic = next(i for i in collect_evidence(case) if i.id == "traffic:window")
        assert "/min" not in traffic.text, case.case_id
        assert set(traffic.data["baseline"]) == {"failed_share", "top_client_share", "top_client"}

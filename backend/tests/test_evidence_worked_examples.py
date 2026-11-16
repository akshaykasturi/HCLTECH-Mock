"""Evidence for the worked examples shows what an engineer needs to see."""
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

    traffic = items["traffic:window"].data["window"]
    assert traffic["top_client_share"] >= 0.5  # one client sends most of the requests
    assert traffic["top_client"] == items["request:c-8f4e3a51a3"].data["client_id"]

    headers = items["request:c-8f4e3a51a3"].data["rate_limit_headers"]
    assert headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in headers
    assert "X-RateLimit-Remaining 0" in items["request:c-8f4e3a51a3"].text

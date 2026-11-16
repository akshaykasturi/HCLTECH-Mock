"""Store lookups and evidence item shape."""
import pytest

from app.uc4.evidence import collect_evidence
from app.uc4.store import get_case, logs_by_correlation_id, logs_for_route

KINDS = {"request", "traffic", "metric", "change", "missing"}


def test_get_case_and_unknown_case() -> None:
    assert get_case("UC4-0050").route == "GET /v1/orders/{id}"
    with pytest.raises(KeyError):
        get_case("UC4-9999")


def test_logs_for_route_stays_inside_the_window() -> None:
    case = get_case("UC4-0050")
    rows = logs_for_route(case.route, case.window_start, case.window_end)
    assert rows
    assert all(r["route"] == case.route for r in rows)
    assert any(r["correlation_id"] == case.focal_correlation_id for r in rows)


def test_logs_by_correlation_id() -> None:
    rows = logs_by_correlation_id("c-1e93f5b875")
    assert len(rows) == 1 and rows[0]["status"] == 504
    assert logs_by_correlation_id("c-nope") == []


def test_items_have_stable_unique_ids_and_known_kinds() -> None:
    first = collect_evidence(get_case("UC4-0074"))
    second = collect_evidence(get_case("UC4-0074"))
    assert [i.id for i in first] == [i.id for i in second]
    assert len({i.id for i in first}) == len(first)
    assert {i.kind for i in first} <= KINDS
    assert all(i.text and "\n" not in i.text for i in first)


def test_changes_are_marked_related_or_unrelated() -> None:
    changes = [i for i in collect_evidence(get_case("UC4-0074")) if i.kind == "change"]
    assert changes, "UC4-0074 (500 after a deploy) should show a change"
    assert all(isinstance(c.data["related"], bool) for c in changes)
    assert any(c.data["related"] for c in changes)

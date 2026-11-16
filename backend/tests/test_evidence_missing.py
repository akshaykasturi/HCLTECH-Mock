"""'missing' items appear when evidence is thin, and not on normal cases."""
import pytest

from app.uc4.evidence import collect_evidence
from app.uc4.models import Case
from app.uc4.store import get_case, load_cases


@pytest.mark.parametrize("case_id", ["UC4-0087", "UC4-0088", "UC4-0089", "UC4-0090"])
def test_insufficient_cases_have_a_missing_item(case_id: str) -> None:
    missing = [i for i in collect_evidence(get_case(case_id)) if i.kind == "missing"]
    assert missing, f"{case_id} should report missing evidence"


def test_401_without_auth_details_is_reported() -> None:
    ids = {i.id for i in collect_evidence(get_case("UC4-0087"))}
    assert "missing:auth_details" in ids


def test_unknown_focal_request_is_reported() -> None:
    case = get_case("UC4-0050").model_copy(update={"focal_correlation_id": "c-does-not-exist"})
    ids = {i.id for i in collect_evidence(case)}
    assert "missing:focal_request" in ids
    assert not any(i.startswith("request:") for i in ids)


def test_labelled_cases_have_no_missing_items() -> None:
    # Labels are used here only to pick the cases; collect_evidence never reads them.
    for case in load_cases().values():
        if case.expected_cause is not None:
            missing = [i.id for i in collect_evidence(case) if i.kind == "missing"]
            assert not missing, f"{case.case_id}: {missing}"


def test_evidence_does_not_depend_on_labels() -> None:
    case = get_case("UC4-0050")
    live = Case(**case.model_dump(include={"case_id", "focal_correlation_id", "route",
                                           "onset_ts", "window_start", "window_end"}))
    assert live.expected_cause is None
    assert collect_evidence(live) == collect_evidence(case)

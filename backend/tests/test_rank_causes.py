"""Cause ranking: worked examples, statuses, confidences, evidence links."""
import pytest

from app.uc4.diagnose import diagnose
from app.uc4.rank import load_catalog, load_likelihoods, posteriors, rank_causes
from app.uc4.signals import get_signals
from app.uc4.store import get_case, load_cases

WORKED = {
    "UC4-0026": "missing_required_field",
    "UC4-0074": "deployment_regression",
    "UC4-0002": "token_expired",
    "UC4-0050": "upstream_dependency_slow",
    "UC4-0038": "client_rate_limit_exceeded",
}


@pytest.fixture(scope="module")
def all_diagnoses() -> dict:
    return {cid: diagnose(case) for cid, case in load_cases().items()}


@pytest.mark.parametrize("case_id,cause", sorted(WORKED.items()))
def test_worked_examples_rank_expected_cause_first(all_diagnoses, case_id: str, cause: str) -> None:
    top = all_diagnoses[case_id].ranked[0]
    assert top.cause == cause, f"{case_id}: got {top.cause}"


def test_confidences_sum_to_one_and_are_sorted(all_diagnoses) -> None:
    for cid, d in all_diagnoses.items():
        confs = [r.confidence for r in d.ranked]
        assert sum(confs) == pytest.approx(1.0, abs=1e-4), cid
        assert confs == sorted(confs, reverse=True), cid
        assert [r.rank for r in d.ranked] == list(range(1, len(d.ranked) + 1))
        assert len(d.ranked) == len(load_likelihoods())


def test_no_cause_is_likely_without_all_confirming_signals(all_diagnoses) -> None:
    catalog = load_catalog()
    for cid, d in all_diagnoses.items():
        for r in d.ranked:
            if r.status == "likely":
                needed = catalog[r.cause]["confirming_signals"]
                assert needed and all(d.signals.get(s) for s in needed), f"{cid} {r.cause}"
                assert not r.confirming_missing


def test_status_never_says_confirmed(all_diagnoses) -> None:
    statuses = {r.status for d in all_diagnoses.values() for r in d.ranked}
    assert statuses <= {"likely", "probable", "unsupported"}


def test_supporting_signals_cite_existing_evidence(all_diagnoses) -> None:
    for cid, d in all_diagnoses.items():
        ids = {item.id for item in d.evidence}
        for r in d.ranked[:3]:
            for link in r.supporting + r.contradicting:
                assert set(link.evidence_ids) <= ids, f"{cid} {r.cause} {link.signal}"


def test_uc4_0038_support_and_contradiction() -> None:
    case = get_case("UC4-0038")
    d = diagnose(case)
    top = d.ranked[0]
    support = {link.signal: link for link in top.supporting}
    assert "traffic_spike" in support
    assert support["traffic_spike"].evidence_ids == ["metric:endpoint:GET /v1/inventory/{sku}"]
    assert "request:c-8f4e3a51a3" in support["code_rate_limited"].evidence_ids
    # retry_storm's key signal (duplicate idempotency keys) is absent: listed against it.
    retry = next(r for r in d.ranked if r.cause == "retry_storm")
    absent = [link.signal for link in retry.contradicting if not link.present]
    assert "duplicate_idempotency_keys" in absent


def test_catalog_fields_flow_through() -> None:
    top = diagnose(get_case("UC4-0050")).ranked[0]
    assert top.first_check == "check_dependency_latency"
    assert top.escalate is True
    assert top.failure_class == "timeout"


def test_unknown_signals_are_ignored_and_none_skipped() -> None:
    signals = get_signals(get_case("UC4-0002"))
    with_extra = {**signals, "not_a_signal": True, "status_500": None}
    assert rank_causes(with_extra, [])[0].cause == "token_expired"
    assert sum(posteriors(with_extra).values()) == pytest.approx(1.0)


def test_signals_do_not_carry_labels() -> None:
    signals = get_signals(get_case("UC4-0002"))
    assert not any(k.startswith("expected_") or k in {"split", "difficulty"} for k in signals)

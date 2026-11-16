"""The gate: CLARIFY only on missing evidence; otherwise RECOMMEND, with alternatives when not a clear win."""
import pytest

from app.uc4.diagnose import run_code_steps as diagnose
from app.uc4.gate import decide
from app.uc4.models import EvidenceItem
from app.uc4.rank import rank_causes
from app.uc4.store import get_case, load_cases


@pytest.fixture(scope="module")
def all_diagnoses() -> dict:
    return {cid: diagnose(case) for cid, case in load_cases().items()}


@pytest.mark.parametrize("case_id", ["UC4-0087", "UC4-0088", "UC4-0089", "UC4-0090"])
def test_insufficient_cases_clarify(all_diagnoses, case_id: str) -> None:
    decision = all_diagnoses[case_id].decision
    assert decision.outcome == "CLARIFY"
    assert decision.missing_info, "CLARIFY must say what is missing"
    assert decision.escalate is False


def test_labelled_cases_never_clarify(all_diagnoses) -> None:
    # Labels pick the cases only. Their evidence is complete, so they must get an answer.
    for cid, d in all_diagnoses.items():
        if d.case.expected_cause is not None:
            assert d.decision.outcome == "RECOMMEND", f"{cid}: {d.decision.reasons}"


def test_worked_example_recommends_and_escalates(all_diagnoses) -> None:
    decision = all_diagnoses["UC4-0074"].decision  # deployment regression: needs privileged access
    assert decision.outcome == "RECOMMEND"
    assert decision.top_cause == "deployment_regression"
    assert decision.escalate is True


def test_clear_winner_has_no_alternatives(all_diagnoses) -> None:
    decision = all_diagnoses["UC4-0038"].decision
    assert decision.outcome == "RECOMMEND" and decision.escalate is False
    assert decision.alternatives == [] and decision.tell_apart is None and not decision.low_confidence


def test_low_confidence_recommends_with_alternatives_not_clarify(all_diagnoses) -> None:
    d = all_diagnoses["UC4-0038"]
    decision = decide(d.ranked, d.signals, d.evidence, threshold=0.99)
    assert decision.outcome == "RECOMMEND"
    assert decision.low_confidence is True
    assert decision.alternatives[0] == decision.top_cause and len(decision.alternatives) >= 2
    assert decision.reasons == []


def test_near_tie_lists_every_tied_cause_with_how_to_tell_them_apart() -> None:
    d = diagnose(get_case("UC4-0038"))
    ranked = rank_causes(d.signals, d.evidence, margin=0.85)  # top 0.90, runner-up 0.10: tied at this margin
    decision = decide(ranked, d.signals, d.evidence)
    tied = [r.cause for r in ranked if r.near_tie]
    assert decision.alternatives == tied
    assert {"client_rate_limit_exceeded", "retry_storm"} <= set(tied)

    apart = decision.tell_apart
    assert apart.causes == tied
    assert apart.first_checks["retry_storm"] == "inspect_retry_policy"
    assert apart.first_checks["client_rate_limit_exceeded"] == "compare_request_rate"
    differ = {s.signal: s for s in apart.signals}
    assert differ["duplicate_idempotency_keys"].favours == "retry_storm"
    assert differ["duplicate_idempotency_keys"].observed is False
    assert "inspect_retry_policy" in apart.note and "duplicate_idempotency_keys" in apart.note

    # Tied causes are "probable": never "likely" (and never "confirmed").
    assert all(r.status == "probable" for r in ranked if r.near_tie)


def test_tell_apart_never_lists_missing_data_signals(all_diagnoses) -> None:
    missing_data = {"metrics_missing", "dep_metrics_missing", "auth_fields_missing", "isolated_failure",
                    "ratelimit_headers_missing", "window_logs_missing"}
    for d in all_diagnoses.values():
        if d.decision.tell_apart:
            assert not {s.signal for s in d.decision.tell_apart.signals} & missing_data


def test_missing_evidence_item_alone_clarifies(all_diagnoses) -> None:
    d = all_diagnoses["UC4-0038"]
    extra = d.evidence + [EvidenceItem(id="missing:endpoint_metrics", kind="missing",
                                       text="Missing: no endpoint metrics")]
    decision = decide(d.ranked, d.signals, extra)
    assert decision.outcome == "CLARIFY"
    assert decision.missing_info == ["no endpoint metrics"]


@pytest.mark.parametrize("signal", ["metrics_missing", "dep_metrics_missing", "auth_fields_missing", "isolated_failure",
                                    "ratelimit_headers_missing"])
def test_each_missing_data_signal_alone_clarifies(all_diagnoses, signal: str) -> None:
    d = all_diagnoses["UC4-0038"]
    decision = decide(d.ranked, {**d.signals, signal: True}, d.evidence)
    assert decision.outcome == "CLARIFY"
    assert any(signal in r for r in decision.reasons)

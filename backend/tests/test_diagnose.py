"""The full diagnose() pipeline: end to end, JSON, trace, and no labels read."""
import json

import pytest

from app.uc4 import diagnose as diagnose_module
from app.uc4.diagnose import diagnose
from app.uc4.models import Case, Diagnosis
from app.uc4.store import get_case

WORKED = {
    "UC4-0026": "missing_required_field",
    "UC4-0074": "deployment_regression",
    "UC4-0002": "token_expired",
    "UC4-0050": "upstream_dependency_slow",
    "UC4-0038": "client_rate_limit_exceeded",
}
STEPS = ["load_case", "collect_evidence", "get_signals", "classifier", "rank_causes", "decide", "report", "checks"]


@pytest.mark.parametrize("case_id,cause", sorted(WORKED.items()))
def test_worked_examples_end_to_end(case_id: str, cause: str) -> None:
    d = diagnose(case_id)
    assert d.outcome == "RECOMMEND"
    assert d.ranked[0].cause == cause
    assert d.report is not None and d.report.causes[0].cause == cause
    assert [f for f in d.report_findings if f.severity == "block"] == []
    assert d.groundedness == 1.0
    assert d.generator == "template"


def test_template_citations_quote_evidence_text_exactly() -> None:
    d = diagnose("UC4-0050")
    texts = {e.id: e.text for e in d.evidence}
    for cause in d.report.causes:
        for cite in cause.supporting + cause.contradicting:
            assert cite.quote == texts[cite.evidence_id]


@pytest.mark.parametrize("case_id", ["UC4-0087", "UC4-0088", "UC4-0089", "UC4-0090"])
def test_insufficient_cases_clarify_without_claiming_a_cause(case_id: str) -> None:
    d = diagnose(case_id)
    assert d.outcome == "CLARIFY" and d.escalate is False
    assert d.missing_info
    assert d.ranked == [] and d.failure_class is None and d.alternatives == []
    assert d.report.outcome == "CLARIFY" and d.report.causes == []
    assert d.report.missing_info and d.report.verification_steps
    assert [f for f in d.report_findings if f.severity == "block"] == []


def test_alternatives_and_tell_apart_come_from_the_gate() -> None:
    d = diagnose("UC4-0048")  # retry_storm vs client_rate_limit_exceeded: not a clear winner
    assert d.alternatives[:2] == ["client_rate_limit_exceeded", "retry_storm"]
    assert d.tell_apart is not None and "inspect_retry_policy" in d.tell_apart.note
    assert [c.cause for c in d.report.causes] == d.alternatives
    assert {c.likelihood for c in d.report.causes} <= {"likely", "probable", "possible"}


def test_class_confidence_sums_the_top_class() -> None:
    d = diagnose("UC4-0048")
    expected = sum(r.confidence for r in d.ranked if r.failure_class == d.failure_class)
    assert d.failure_class == "rate_limit"
    assert d.class_confidence == pytest.approx(expected, abs=1e-5)
    assert d.class_confidence >= d.ranked[0].confidence


def test_diagnosis_converts_to_json_and_back() -> None:
    d = diagnose("UC4-0050")
    payload = d.model_dump_json()
    data = json.loads(payload)
    assert data["case_id"] == "UC4-0050" and data["outcome"] == "RECOMMEND"
    assert isinstance(data["diagnosis_id"], str) and data["created_at"]
    assert Diagnosis.model_validate_json(payload) == d


def test_trace_has_every_step_in_order() -> None:
    d = diagnose("UC4-0050")
    assert [t.step for t in d.trace] == STEPS
    assert all(t.ms >= 0 for t in d.trace)


def test_missing_teammate_pieces_are_noted_not_fatal() -> None:
    trace = {t.step: t.detail for t in diagnose("UC4-0050").trace}
    assert "not available yet" in trace["classifier"]
    assert "used the code template" in trace["report"]


def test_broken_teammate_pieces_fall_back(monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(diagnose_module, "_optional", lambda module, name: broken)
    d = diagnose("UC4-0050")
    trace = {t.step: t.detail for t in d.trace}
    assert "classifier failed (RuntimeError)" in trace["classifier"]
    assert "write_report failed (RuntimeError)" in trace["report"]
    assert d.generator == "template" and d.ranked[0].cause == "upstream_dependency_slow"


def test_labels_are_never_read() -> None:
    real = get_case("UC4-0050")
    # Same case with wrong labels, and with no labels at all: the diagnosis must not change.
    wrong = real.model_copy(update={"expected_cause": "token_expired", "expected_class": "authentication",
                                    "expected_outcome": "CLARIFY", "missing_info": ["something"],
                                    "requires_escalation": False, "culprit_dependency": "nope",
                                    "generation": {"expected_signals_on": []}})
    bare = Case(**real.model_dump(include={"case_id", "focal_correlation_id", "route",
                                           "onset_ts", "window_start", "window_end"}))
    skip = {"diagnosis_id", "created_at", "trace"}
    a, b, c = (diagnose(x).model_dump(exclude=skip) for x in (real, wrong, bare))
    assert a == b == c


def test_template_report_has_no_blocking_findings_on_all_90_cases() -> None:
    from app.uc4.store import load_cases
    for cid in load_cases():
        d = diagnose(cid)
        blocking = [(f.code, f.where) for f in d.report_findings if f.severity == "block"]
        assert blocking == [], f"{cid}: {blocking}"


def test_groundedness_is_none_when_nothing_is_cited() -> None:
    d = diagnose("UC4-0087")  # CLARIFY: no causes, nothing to cite
    assert d.groundedness is None
    assert diagnose("UC4-0050").groundedness == 1.0


def test_steps_are_readable_checks_citing_a_troubleshooting_doc() -> None:
    from app.uc4.template_report import load_checks_text
    d = diagnose("UC4-0038")
    step = d.report.verification_steps[0]
    assert step.action == load_checks_text()["causes"]["client_rate_limit_exceeded"]["check_text"]
    assert "check check" not in step.action.lower() and "check check" not in step.why.lower()
    assert any(c.startswith("doc:troubleshooting#") for c in step.cites)


def test_escalation_names_the_owner_and_never_says_a_check_is_privileged() -> None:
    for cid in ("UC4-0050", "UC4-0074", "UC4-0038", "UC4-0002"):
        esc = diagnose(cid).report.escalation
        assert esc.team and "read-only and need no special access" in esc.reason
        assert "needs privileged access" not in esc.reason  # the fix may be privileged; a check never is
    assert "database team" in diagnose("UC4-0050").report.escalation.team  # orders-db
    assert "cli_" in diagnose("UC4-0038").report.escalation.team  # the client fixes a rate-limit problem


def test_explanation_says_which_signal_points_each_way() -> None:
    d = diagnose("UC4-0050")  # the endpoint metric shows a latency spike (for) and an error spike (against)
    explanation = d.report.causes[0].explanation
    assert "points both ways" in explanation
    assert "error_rate_spike" in explanation.split("points both ways")[1]


def test_confidence_display_rounds_only_for_people() -> None:
    from app.uc4.display import format_confidence
    assert format_confidence(0.9996) == "> 0.99" and format_confidence(0.00004) == "< 0.01"
    assert format_confidence(0.6) == "0.60"
    d = diagnose("UC4-0050")
    assert d.ranked[0].confidence > 0.99  # the stored number is unchanged

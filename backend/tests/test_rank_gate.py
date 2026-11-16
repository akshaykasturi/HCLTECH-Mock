"""The CLARIFY gate."""
import pytest

from app.uc4.diagnose import diagnose
from app.uc4.gate import decide
from app.uc4.models import EvidenceItem
from app.uc4.store import get_case


@pytest.mark.parametrize("case_id", ["UC4-0087", "UC4-0088", "UC4-0089", "UC4-0090"])
def test_insufficient_cases_clarify(case_id: str) -> None:
    d = diagnose(get_case(case_id))
    assert d.decision.outcome == "CLARIFY"
    assert d.decision.missing_info, "CLARIFY must say what is missing"
    assert d.decision.escalate is False


def test_worked_example_recommends_and_escalates() -> None:
    d = diagnose(get_case("UC4-0074"))  # deployment regression: diff the deploy, needs privileged access
    assert d.decision.outcome == "RECOMMEND"
    assert d.decision.top_cause == "deployment_regression"
    assert d.decision.escalate is True


def test_rate_limit_example_recommends_without_escalation() -> None:
    d = diagnose(get_case("UC4-0038"))
    assert d.decision.outcome == "RECOMMEND" and d.decision.escalate is False


def test_low_confidence_clarifies() -> None:
    d = diagnose(get_case("UC4-0038"))
    decision = decide(d.ranked, d.signals, d.evidence, threshold=0.99)
    assert decision.outcome == "CLARIFY"
    assert any("below the threshold" in r for r in decision.reasons)


def test_missing_evidence_item_alone_clarifies() -> None:
    d = diagnose(get_case("UC4-0038"))
    extra = d.evidence + [EvidenceItem(id="missing:endpoint_metrics", kind="missing",
                                       text="Missing: no endpoint metrics")]
    decision = decide(d.ranked, d.signals, extra)
    assert decision.outcome == "CLARIFY"
    assert decision.missing_info == ["no endpoint metrics"]


def test_missing_data_signal_alone_clarifies() -> None:
    d = diagnose(get_case("UC4-0038"))
    decision = decide(d.ranked, {**d.signals, "metrics_missing": True}, d.evidence)
    assert decision.outcome == "CLARIFY"
    assert any("metrics_missing" in r for r in decision.reasons)

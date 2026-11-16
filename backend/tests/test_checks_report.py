"""Output checks on the report (checks.py). No network, no LLM.

A valid report for UC4-0050 (orders-db slow -> 504) is built by quoting real evidence lines.
Each test then breaks one thing and checks that it is blocked.
"""
import pytest

from app.uc4.checks import (apply_findings, check_certainty, check_citations, check_consistency,
                            check_known_causes, check_numbers, check_report, check_safe_steps,
                            check_secrets, groundedness)
from app.uc4.evidence import collect_evidence
from app.uc4.report_models import Citation, Escalation, Report, ReportCause, Step
from app.uc4.store import get_case

ALLOWED = ["upstream_dependency_slow", "client_timeout_too_low", "dependency_outage"]
REQ = "request:c-1e93f5b875"
DB = "metric:service:orders-db"
ENDPOINT = "metric:endpoint:GET /v1/orders/{id}"


@pytest.fixture(scope="module")
def evidence():
    return collect_evidence(get_case("UC4-0050"))


def valid_report() -> Report:
    return Report(
        case_id="UC4-0050",
        outcome="RECOMMEND",
        summary=("GET /v1/orders/{id} returned 504 for 17 of 44 requests in the window (error rate 38.6%); "
                 "orders-db p95 rose from 19.43 ms to 161 ms."),
        causes=[
            ReportCause(
                cause="upstream_dependency_slow",
                likelihood="likely",
                explanation=("Request c-1e93f5b875 waited 10,004 ms for orders-db, and orders-db p95 was "
                             "161 ms against a 19.43 ms baseline (x8.27). This is likely, not confirmed."),
                supporting=[
                    Citation(evidence_id=REQ, quote="Upstream orders-db did not respond within 10000 ms"),
                    Citation(evidence_id=DB, quote="p95 161 ms vs 19.43 ms (x8.27, peak 306 ms)"),
                ],
                contradicting=[Citation(evidence_id=DB, quote="error rate 0.1% vs 0.1% (x1.1)")],
            ),
            ReportCause(
                cause="client_timeout_too_low",
                likelihood="possible",
                explanation="The request stopped at 10 s, the same as the 10000 ms upstream limit.",
                supporting=[Citation(evidence_id=REQ, quote="GET /v1/orders/{id} -> 504 in 10,004 ms")],
            ),
        ],
        verification_steps=[
            Step(action="Look at the orders-db slow query log for the incident window",
                 why="orders-db p95 went from 19.43 ms to 161 ms", cites=[DB]),
            Step(action="Compare the endpoint p95 with the orders-db p95",
                 why="endpoint p95 was 6,393 ms vs 111 ms (x57.61)", cites=[ENDPOINT]),
        ],
        escalation=Escalation(needed=False),
    )


def blocks(findings, code=None):
    return [f for f in findings if f.severity == "block" and (code is None or f.code == code)]


# ---------- the valid report passes ----------

def test_valid_report_has_no_block_and_full_groundedness(evidence) -> None:
    report = valid_report()
    assert blocks(check_report(report, evidence, ALLOWED)) == []
    assert groundedness(report, evidence) == 1.0


# ---------- citations ----------

def test_unknown_evidence_id_is_blocked(evidence) -> None:
    report = valid_report()
    report.causes[0].supporting[1].evidence_id = "metric:service:payments-db"
    found = blocks(check_citations(report, evidence), "CITE_UNKNOWN_ID")
    assert [f.where for f in found] == ["causes[0].supporting[1]"]
    assert groundedness(report, evidence) == pytest.approx(3 / 4)


def test_quote_not_in_text_is_blocked(evidence) -> None:
    report = valid_report()
    report.causes[0].supporting[0].quote = "orders-db returned 503 Service Unavailable"
    assert [f.where for f in blocks(check_citations(report, evidence), "CITE_QUOTE_NOT_FOUND")] == [
        "causes[0].supporting[0]"]


def test_quote_ignores_case_and_extra_spaces(evidence) -> None:
    report = valid_report()
    report.causes[0].supporting[0].quote = "  UPSTREAM orders-db   did not respond\nwithin 10000 ms "
    assert blocks(check_citations(report, evidence)) == []


def test_cause_without_supporting_citation_is_blocked(evidence) -> None:
    report = valid_report()
    report.causes[1].supporting = []
    assert [f.where for f in blocks(check_citations(report, evidence), "CAUSE_NO_SUPPORT")] == ["causes[1]"]


# ---------- known causes ----------

def test_invented_cause_is_blocked() -> None:
    report = valid_report()
    report.causes[1].cause = "cache_stampede"
    assert [f.where for f in blocks(check_known_causes(report, ALLOWED), "CAUSE_UNKNOWN")] == ["causes[1]"]


# ---------- numbers ----------

def test_changed_number_is_blocked(evidence) -> None:
    report = valid_report()
    report.summary = report.summary.replace("161 ms", "4,800 ms")  # evidence says 161
    found = blocks(check_numbers(report, evidence), "NUMBER_NOT_IN_EVIDENCE")
    assert [f.where for f in found] == ["summary"]
    assert "4,800" in found[0].message


def test_number_must_be_in_the_cited_items(evidence) -> None:
    report = valid_report()
    # 6,393 is real (endpoint metric) but this cause does not cite the endpoint metric.
    report.causes[0].explanation += " The endpoint p95 was 6,393 ms."
    assert [f.where for f in blocks(check_numbers(report, evidence))] == ["causes[0].explanation"]


@pytest.mark.parametrize("text", [
    "10004 ms",           # 1,234 vs 1234
    "about 10 s",         # seconds vs milliseconds
    "error rate 0.3864",  # 38.6% vs 0.3864
    "x57.61 on p95",      # a ratio
    "until 05:22:42",     # a time from the evidence
])
def test_number_formats_are_normalised(evidence, text) -> None:
    report = valid_report()
    report.summary = f"GET /v1/orders/{{id}} failed: {text}."
    assert blocks(check_numbers(report, evidence)) == []


def test_ids_routes_and_status_codes_are_not_numbers(evidence) -> None:
    report = valid_report()
    report.summary = f"See {ENDPOINT} and {REQ} for UC4-0050: HTTP 504 with p95 and v1 routes."
    assert blocks(check_numbers(report, evidence)) == []


def test_status_code_not_in_evidence_is_checked(evidence) -> None:
    report = valid_report()
    report.summary = "The route returned 503."  # the evidence only has 200 and 504
    assert blocks(check_numbers(report, evidence))


# ---------- certainty ----------

def test_confirmed_root_cause_is_blocked() -> None:
    report = valid_report()
    report.causes[0].explanation = "The root cause is confirmed: orders-db was slow."
    codes = blocks(check_certainty(report), "CERTAINTY")
    assert {f.where for f in codes} == {"causes[0].explanation"}


@pytest.mark.parametrize("text", [
    "Likely orders-db, but not confirmed.",
    "This cannot be confirmed without the slow query log.",
    "The root cause is not known yet.",
])
def test_negated_certainty_passes(text) -> None:
    report = valid_report()
    report.summary = text
    assert blocks(check_certainty(report)) == []


@pytest.mark.parametrize("text", ["It is definitely orders-db.", "We are 100% sure.", "This is proven."])
def test_certainty_words_in_summary_are_blocked(text) -> None:
    report = valid_report()
    report.summary = text
    assert [f.where for f in blocks(check_certainty(report))] == ["summary"]


# ---------- safe steps ----------

def test_restart_step_is_blocked_but_escalation_may_mention_it() -> None:
    report = valid_report()
    report.verification_steps.append(Step(action="Restart the database", why="clears slow queries"))
    report.escalation = Escalation(needed=True, team="db-oncall", reason="May need a restart of orders-db.")
    found = blocks(check_safe_steps(report), "UNSAFE_STEP")
    assert [f.where for f in found] == ["verification_steps[2].action"]
    assert "move to escalation" in found[0].message


@pytest.mark.parametrize("action", ["Roll back the last deploy", "Rotate the API key",
                                    "Flush the cache", "Change the allowlist for this client"])
def test_other_changing_steps_are_blocked(action) -> None:
    report = valid_report()
    report.verification_steps = [Step(action=action, why="to fix it")]
    assert blocks(check_safe_steps(report))


# ---------- secrets ----------

def test_api_key_in_summary_is_blocked() -> None:
    fake_key = "nvp_live_" + "Zz9" * 8  # built here, not copied from the logs
    report = valid_report()
    report.summary += f" The client used {fake_key}."
    found = blocks(check_secrets(report), "SECRET")
    assert [f.where for f in found] == ["summary"]
    assert fake_key not in found[0].message  # the finding never repeats the secret


def test_masked_key_prefix_is_not_a_secret() -> None:
    report = valid_report()
    report.summary += " The client used a nvp_live_<KEY> key."
    assert blocks(check_secrets(report)) == []


# ---------- consistency ----------

def test_clarify_without_missing_info_is_blocked() -> None:
    report = valid_report()
    report.outcome = "CLARIFY"
    assert blocks(check_consistency(report), "CLARIFY_NO_MISSING_INFO")
    report.missing_info = ["orders-db slow query log"]
    assert blocks(check_consistency(report)) == []


def test_escalate_needs_escalation() -> None:
    report = valid_report()
    report.outcome = "ESCALATE"
    assert blocks(check_consistency(report), "ESCALATE_NOT_NEEDED")


# ---------- apply_findings ----------

def test_apply_findings_drops_only_the_bad_parts(evidence) -> None:
    report = valid_report()
    report.causes[0].supporting[1].quote = "orders-db p95 was 4,800 ms"  # bad citation, cause keeps one
    report.causes[1].supporting[0].evidence_id = "request:c-unknown"  # only citation of cause 2
    report.verification_steps.append(Step(action="Restart the database", why="clears slow queries"))

    fixed = apply_findings(report, check_report(report, evidence, ALLOWED))

    assert [c.cause for c in fixed.causes] == ["upstream_dependency_slow"]
    assert len(fixed.causes[0].supporting) == 1
    assert len(fixed.verification_steps) == 2
    assert fixed.outcome == "RECOMMEND"
    assert blocks(check_report(fixed, evidence, ALLOWED)) == []
    assert groundedness(fixed, evidence) == 1.0
    assert len(report.causes) == 2  # the input is not changed


def test_apply_findings_falls_back_to_clarify(evidence) -> None:
    report = valid_report()
    report.causes[0].cause = "cache_stampede"
    report.causes[1].explanation = "The root cause is definitely the client timeout."

    fixed = apply_findings(report, check_report(report, evidence, ALLOWED))

    assert fixed.causes == []
    assert fixed.outcome == "CLARIFY"
    assert fixed.missing_info  # says why there is no cause
    assert blocks(check_report(fixed, evidence, ALLOWED)) == []


def test_apply_findings_replaces_a_leaking_summary(evidence) -> None:
    report = valid_report()
    report.summary += " Contact ops-" + "team@example.com"
    fixed = apply_findings(report, check_report(report, evidence, ALLOWED))
    assert check_secrets(fixed) == []
    assert "@" not in fixed.summary

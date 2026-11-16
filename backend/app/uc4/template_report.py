"""A report built by code only, used until an LLM writes reports (Atheesha's write_report).

It must pass the same output checks as an LLM report (checks.py), so it is written carefully:
  - every citation quotes EvidenceItem.text word for word;
  - no confidences or other numbers of our own in the text (only status codes, which the checks allow);
  - likelihood is "likely" or "probable" (or "possible"), never "confirmed";
  - verification steps are read-only first checks; privileged ones go to escalation.
On CLARIFY no cause is claimed: the report lists what is missing and read-only steps to collect it.
"""
from typing import Optional

from app.uc4.models import Case, EvidenceItem, GateDecision, RankedCause, SignalLink
from app.uc4.report_models import Citation, Escalation, Report, ReportCause, Step
from app.uc4.settings import get_settings

_LIKELIHOOD = {"likely": "likely", "probable": "probable", "unsupported": "possible"}


def _focal_status(evidence: list[EvidenceItem]) -> Optional[int]:
    for item in evidence:
        if item.kind == "request":
            return item.data.get("status")
    return None


def _citations(links: list[SignalLink], by_id: dict[str, EvidenceItem]) -> list[Citation]:
    """One citation per evidence item the links point to (first time it appears), quoting its text exactly."""
    seen: list[str] = []
    for link in links:
        for evidence_id in link.evidence_ids:
            if evidence_id in by_id and evidence_id not in seen:
                seen.append(evidence_id)
    return [Citation(evidence_id=i, quote=by_id[i].text) for i in seen]


def _explanation(cause: RankedCause) -> str:
    """Built from the signal links. Signal names only: no numbers of our own."""
    parts = []
    if cause.supporting:
        parts.append("Signals that fit this cause better than the others: "
                     + ", ".join(link.signal for link in cause.supporting) + ".")
    against_on = [link.signal for link in cause.contradicting if link.present]
    against_off = [link.signal for link in cause.contradicting if not link.present]
    if against_on:
        parts.append("Signals that fit other causes better: " + ", ".join(against_on) + ".")
    if against_off:
        parts.append("Expected but not seen: " + ", ".join(against_off) + ".")
    if cause.confirming_missing:
        parts.append("Not all of its confirming signals were seen: " + ", ".join(cause.confirming_missing) + ".")
    return " ".join(parts) or "No single signal stands out for this cause."


def _route_team(route: str) -> str:
    service = get_settings()["routes"].get(route, {}).get("service")
    return f"{service} owners" if service else "service owners"


def build_report(case: Case, ranked: list[RankedCause], decision: GateDecision,
                 evidence: list[EvidenceItem]) -> Report:
    by_id = {item.id: item for item in evidence}
    status = _focal_status(evidence)
    failure = f"{status} on {case.route}" if status else f"Failure on {case.route}"

    if decision.outcome == "CLARIFY":
        missing = [item for item in evidence if item.kind == "missing"]
        steps = [Step(action=f"Collect the missing information: {item.text.removeprefix('Missing: ')}",
                      why="A cause can only be named once this information is available.", cites=[item.id])
                 for item in missing]
        if not steps:
            steps = [Step(action="Collect the data behind the missing-data signals listed in missing info",
                          why="A cause can only be named once this information is available.")]
        return Report(
            case_id=case.case_id, outcome="CLARIFY",
            summary=f"{failure}: not enough evidence to name a likely cause yet. See missing info.",
            causes=[], verification_steps=steps,
            escalation=Escalation(needed=False), missing_info=list(decision.missing_info),
        )

    shown = decision.alternatives or [ranked[0].cause]
    by_cause = {r.cause: r for r in ranked}
    causes, steps = [], []
    for name in shown:
        r = by_cause[name]
        causes.append(ReportCause(
            cause=r.cause, likelihood=_LIKELIHOOD[r.status], explanation=_explanation(r),
            supporting=_citations(r.supporting, by_id),
            contradicting=_citations([link for link in r.contradicting if link.present], by_id),
        ))
        cites = [c.evidence_id for c in causes[-1].supporting]
        steps.append(Step(action=f"Run the read-only check {r.first_check} for {r.cause}",
                          why=f"It is the first check for {r.cause} and tests whether it explains the failure.",
                          cites=cites))

    top = ranked[0]
    if len(shown) > 1:
        summary = (f"{failure}: not a clear winner between {', '.join(shown)}. "
                   f"{top.cause} ranks first; run the checks below to tell them apart.")
    else:
        summary = f"{failure}: the most likely cause is {top.cause} ({top.failure_class})."
    escalation = Escalation(
        needed=decision.escalate,
        team=_route_team(case.route) if decision.escalate else "",
        reason=(f"The first check {top.first_check} needs privileged access; a person with that access "
                f"should run it and decide any fix.") if decision.escalate else "",
    )
    return Report(case_id=case.case_id, outcome="RECOMMEND", summary=summary, causes=causes,
                  verification_steps=steps, escalation=escalation, missing_info=list(decision.missing_info))

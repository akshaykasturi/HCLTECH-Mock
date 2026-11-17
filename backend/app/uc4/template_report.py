"""A report built by code only, used until an LLM writes reports (Atheesha's write_report).

It must pass the same output checks as an LLM report (checks.py), so it is written carefully:
  - every citation quotes EvidenceItem.text word for word;
  - no numbers of our own in the text (confidences stay out: they are not evidence; see display.py);
  - likelihood is "likely" or "probable" (or "possible"), never "confirmed";
  - steps are the readable read-only checks from checks_text.yaml, citing the cause's evidence and the
    matching troubleshooting doc section; who owns the FIX goes to escalation.
On CLARIFY no cause is claimed: the report lists what is missing and read-only steps to collect it.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.uc4.models import Case, EvidenceItem, GateDecision, RankedCause, SignalLink
from app.uc4.report_models import Citation, Escalation, Report, ReportCause, Step
from app.uc4.settings import get_settings

CHECKS_TEXT = Path(__file__).with_name("checks_text.yaml")
_LIKELIHOOD = {"likely": "likely", "probable": "probable", "unsupported": "possible"}


@lru_cache(maxsize=1)
def load_checks_text() -> dict[str, Any]:
    """{"causes": {cause: {check_text, owner, owner_why, source}}, "dependencies": {name: owner}}."""
    return yaml.safe_load(CHECKS_TEXT.read_text(encoding="utf-8"))


def _request(evidence: list[EvidenceItem]) -> Optional[EvidenceItem]:
    return next((item for item in evidence if item.kind == "request"), None)


def _citations(links: list[SignalLink], by_id: dict[str, EvidenceItem]) -> list[Citation]:
    """One citation per evidence item the links point to (first time it appears), quoting its text exactly."""
    seen: list[str] = []
    for link in links:
        for evidence_id in link.evidence_ids:
            if evidence_id in by_id and evidence_id not in seen:
                seen.append(evidence_id)
    return [Citation(evidence_id=i, quote=by_id[i].text) for i in seen]


def _explanation(cause: RankedCause) -> str:
    """Built from the signal links: signal names only, no numbers of our own."""
    parts = []
    if cause.supporting:
        parts.append("Signals that fit this cause better than the others: "
                     + ", ".join(link.signal for link in cause.supporting) + ".")
    against_on = [link for link in cause.contradicting if link.present]
    against_off = [link.signal for link in cause.contradicting if not link.present]
    if against_on:
        parts.append("Signals that fit other causes better: " + ", ".join(link.signal for link in against_on) + ".")
    # One evidence item can show several signals: say which way each one points.
    for_by_id: dict[str, list[str]] = {}
    for link in cause.supporting:
        for i in link.evidence_ids:
            for_by_id.setdefault(i, []).append(link.signal)
    for link in against_on:
        for i in link.evidence_ids:
            if i in for_by_id:
                parts.append(f"The same evidence {i} points both ways: {', '.join(for_by_id[i])} "
                             f"fits this cause, while {link.signal} fits other causes better.")
    if against_off:
        parts.append("Expected but not seen: " + ", ".join(against_off) + ".")
    if cause.confirming_missing:
        parts.append("Not all of its confirming signals were seen: " + ", ".join(cause.confirming_missing) + ".")
    return " ".join(parts) or "No single signal stands out for this cause."


def _troubleshooting_doc(cause: str, by_id: dict[str, EvidenceItem]) -> Optional[str]:
    """The doc section to cite with a check: the cause's own source section if doc search found it,
    else the best troubleshooting section doc search found for this error."""
    source = load_checks_text()["causes"].get(cause, {}).get("source")
    if source in by_id:
        return source
    docs = [item for item in by_id.values() if item.kind == "doc"]
    trouble = [d for d in docs if d.data.get("doc_id") == "troubleshooting"]
    return trouble[0].id if trouble else None


def _dependency(case: Case, evidence: list[EvidenceItem]) -> Optional[str]:
    """The dependency involved: the focal request's upstream, else the one whose p95 rose most."""
    request = _request(evidence)
    if request and request.data.get("upstream_service"):
        return request.data["upstream_service"]
    deps = [e for e in evidence if e.kind == "metric" and e.data.get("kind") == "service"]
    if deps:
        return max(deps, key=lambda e: e.data["p95_ms"].get("ratio") or 0).data["target"]
    routes = get_settings()["routes"].get(case.route, {})
    return (routes.get("dependencies") or [None])[0]


def owner_of(cause: str, case: Case, evidence: list[EvidenceItem]) -> tuple[str, str]:
    """(who owns the fix, why them) for a cause, filled in from the case."""
    entry = load_checks_text()["causes"].get(cause, {})
    owner, why = entry.get("owner", "the service owners"), entry.get("owner_why", "")
    if owner == "{client}":
        request = _request(evidence)
        client = request.data.get("client_id") if request else None
        owner = f"the client application team ({client})" if client else "the client application team"
    elif owner == "@dependency":
        dep = _dependency(case, evidence)
        team = load_checks_text()["dependencies"].get(dep) if dep else None
        owner = f"{team} (owner of {dep})" if team else (f"the owners of {dep}" if dep else "the dependency owners")
    elif owner == "@service":
        service = get_settings()["routes"].get(case.route, {}).get("service")
        owner = f"the {service} owners" if service else "the service owners"
    return owner, why


def _step(cause: RankedCause, report_cause: ReportCause, by_id: dict[str, EvidenceItem]) -> Step:
    text = load_checks_text()["causes"].get(cause.cause, {}).get("check_text") or f"Run {cause.first_check}"
    cites = [c.evidence_id for c in report_cause.supporting]
    doc = _troubleshooting_doc(cause.cause, by_id)
    if doc and doc not in cites:
        cites.append(doc)
    return Step(action=text, why=f"Read-only first check for {cause.cause} ({cause.first_check}).", cites=cites)


def build_report(case: Case, ranked: list[RankedCause], decision: GateDecision,
                 evidence: list[EvidenceItem]) -> Report:
    by_id = {item.id: item for item in evidence}
    request = _request(evidence)
    status = request.data.get("status") if request else None
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
        rc = ReportCause(
            cause=r.cause, likelihood=_LIKELIHOOD[r.status], explanation=_explanation(r),
            supporting=_citations(r.supporting, by_id),
            contradicting=_citations([link for link in r.contradicting if link.present], by_id),
        )
        causes.append(rc)
        steps.append(_step(r, rc, by_id))

    top = ranked[0]
    if len(shown) > 1:
        summary = (f"{failure}: not a clear winner between {', '.join(shown)}. "
                   f"{top.cause} ranks first; the checks below tell them apart.")
    else:
        summary = f"{failure}: the {_LIKELIHOOD[top.status]} cause is {top.cause} ({top.failure_class})."

    owner, why = owner_of(top.cause, case, evidence)
    read_only = "The checks above are read-only and need no special access."
    if decision.escalate:
        reason = f"If {top.cause} holds, the fix is a privileged change owned by {owner}. {why} {read_only}"
    else:
        reason = f"No escalation needed: if {top.cause} holds, the fix is owned by {owner}. {why} {read_only}"
    return Report(case_id=case.case_id, outcome="RECOMMEND", summary=summary, causes=causes,
                  verification_steps=steps, escalation=Escalation(needed=decision.escalate, team=owner, reason=reason),
                  missing_info=list(decision.missing_info))

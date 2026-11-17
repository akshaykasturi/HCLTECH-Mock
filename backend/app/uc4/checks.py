"""Output checks for the LLM report (plan step 9: code checks the report before anyone sees it).

Every check is pure: it reads the report (and the evidence) and returns a list of Findings.
Nothing is changed and nothing is printed. A "block" finding means that part must not be shown;
apply_findings() then removes the blocked parts.

  check_citations     evidence ids exist, quotes are copied from that item's text, every cause has support
  check_known_causes  only causes from the ranked list code gave the LLM
  check_numbers       every number in summary / explanation / why is found in the evidence
  check_certainty     no "confirmed", "definitely", "the root cause is"... unless negated
  check_safe_steps    no changing or privileged actions in verification steps (move to escalation)
  check_secrets       no token, API key, email or IP anywhere in the report
  check_consistency   CLARIFY lists missing info; ESCALATE says escalation is needed

Word lists and settings live in checks.yaml.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from app.uc4.models import EvidenceItem
from app.uc4.redact import find_leaks
from app.uc4.report_models import Finding, Report

_CHECKS_FILE = Path(__file__).with_name("checks.yaml")


@lru_cache(maxsize=1)
def get_check_settings() -> dict[str, Any]:
    with _CHECKS_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _block(code: str, message: str, where: str) -> Finding:
    return Finding(code=code, severity="block", message=message, where=where)


def _norm(text: str) -> str:
    """Lower case, one space between words: so quotes match whatever the spacing or case."""
    return " ".join(text.lower().split())


def _by_id(evidence: Iterable[EvidenceItem]) -> dict[str, EvidenceItem]:
    return {item.id: item for item in evidence}


# ---------- citations ----------

def _citation_problem(evidence_id: str, quote: str, by_id: dict[str, EvidenceItem]) -> Optional[tuple[str, str]]:
    """(code, message) if the citation cannot be verified, None if it is fine."""
    item = by_id.get(evidence_id)
    if item is None:
        return "CITE_UNKNOWN_ID", f"evidence id {evidence_id!r} does not exist for this case"
    q = _norm(quote)
    if len(q) < get_check_settings()["citations"]["min_quote_chars"]:
        return "CITE_QUOTE_TOO_SHORT", "the quote is too short to show anything"
    if q not in _norm(item.text):
        return "CITE_QUOTE_NOT_FOUND", f"the quote is not in the text of {evidence_id!r}"
    return None


def check_citations(report: Report, evidence: list[EvidenceItem]) -> list[Finding]:
    by_id = _by_id(evidence)
    findings: list[Finding] = []
    for i, cause in enumerate(report.causes):
        if not cause.supporting:
            findings.append(_block("CAUSE_NO_SUPPORT", "a cause needs at least one supporting citation",
                                   f"causes[{i}]"))
        for side in ("supporting", "contradicting"):
            for j, c in enumerate(getattr(cause, side)):
                problem = _citation_problem(c.evidence_id, c.quote, by_id)
                if problem:
                    findings.append(_block(*problem, f"causes[{i}].{side}[{j}]"))
    for i, step in enumerate(report.verification_steps):
        for j, evidence_id in enumerate(step.cites):
            if evidence_id not in by_id:
                findings.append(_block("CITE_UNKNOWN_ID", f"evidence id {evidence_id!r} does not exist for this case",
                                       f"verification_steps[{i}].cites[{j}]"))
    return findings


def groundedness(report: Report, evidence: list[EvidenceItem]) -> float:
    """Share of the causes' citations that pass the citation check (0..1). No citations -> 0."""
    by_id = _by_id(evidence)
    citations = [c for cause in report.causes for c in cause.supporting + cause.contradicting]
    if not citations:
        return 0.0
    ok = sum(1 for c in citations if _citation_problem(c.evidence_id, c.quote, by_id) is None)
    return ok / len(citations)


# ---------- known causes ----------

def check_known_causes(report: Report, allowed_causes: list[str]) -> list[Finding]:
    allowed = set(allowed_causes)
    return [_block("CAUSE_UNKNOWN", f"cause {c.cause!r} is not in the ranked list", f"causes[{i}]")
            for i, c in enumerate(report.causes) if c.cause not in allowed]


# ---------- numbers ----------

# Times (05:17 or 05:17:22) and dates (2026-10-15, with an optional time) are checked as text.
_TIME_RE = re.compile(r"(?<![\w:])\d{1,2}:\d{2}(?::\d{2})?(?![\w:])")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?")
# Routes like /v1/orders/{id}: their digits are not numbers to check.
_ROUTE_RE = re.compile(r"/[\w/{}.-]*")
# A number: 1,234 or 1234 or 12.5, an optional "x" in front (x8.27), an optional % and unit.
# Digits glued to letters or dashes (p95, v1, c-1e93f5b875, top-3) are part of a name: skipped.
_NUMBER_RE = re.compile(
    r"(?<![\w.,/:-])[x×]?(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?(?P<pct>\s?%)?"
    r"(?P<tail>[A-Za-z_]*+)(?![\d-])(?:\s*(?P<unit>ms|seconds|secs|sec|s|minutes|mins|min)\b)?"
)
_SECONDS = {"s", "sec", "secs", "seconds"}
_MINUTES = {"min", "mins", "minutes"}


def _numbers(text: str) -> list[dict[str, Any]]:
    """Numbers in a piece of text: value, decimals shown, percent?, unit."""
    out = []
    for m in _NUMBER_RE.finditer(text):
        tail = m.group("tail").lower()
        unit = m.group("unit") or (tail if tail in _SECONDS | _MINUTES | {"ms"} else None)
        if tail and tail != unit:
            continue  # e.g. "2xx" or "1e93f": part of a name, not a number
        frac = m.group("frac") or ""
        out.append({"text": m.group(0).strip(), "value": float(m.group("int").replace(",", "") + frac),
                    "decimals": max(len(frac) - 1, 0), "pct": bool(m.group("pct")), "unit": unit})
    return out


def _data_values(value: Any) -> Iterable[float]:
    """Every number inside an evidence item's data (dict keys too: status_counts {"504": 17})."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, str):
        try:
            yield float(value)
        except ValueError:
            pass
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _data_values(k)
            yield from _data_values(v)
    elif isinstance(value, list):
        for v in value:
            yield from _data_values(v)


def _pool(items: list[EvidenceItem]) -> tuple[list[float], str]:
    """All numbers found in these items (text and data), and their text for times and dates."""
    values: list[float] = []
    for item in items:
        for n in _numbers(item.text):
            values.append(n["value"])
            if n["pct"]:
                values.append(n["value"] / 100)
        values.extend(_data_values(item.data))
    text = " ".join(item.text + " " + json.dumps(item.data, default=str) for item in items)
    return values, text


def _status_codes(evidence: list[EvidenceItem]) -> set[float]:
    """HTTP status codes seen in the evidence: "504" is a status, not a measurement."""
    codes: set[float] = set()
    for item in evidence:
        for key in ("status", "upstream_status"):
            if isinstance(item.data.get(key), int):
                codes.add(float(item.data[key]))
        if item.kind == "traffic":
            for side in ("window", "baseline"):
                codes.update(float(k) for k in item.data.get(side, {}).get("status_counts", {}))
    return codes


def _matches(n: dict[str, Any], pool: list[float]) -> bool:
    """True if the number (in any of its readings: %, s vs ms, min vs s) is in the pool."""
    v = n["value"]
    half = 0.5 * 10 ** -n["decimals"]  # "161" covers 160.5..161.5; "38.6" covers 38.55..38.65
    readings = [(v, half)]
    if n["pct"]:
        readings.append((v / 100, half / 100))  # 12.5% vs 0.125
    if n["unit"] in _SECONDS:
        readings.append((v * 1000, half * 1000))  # 10 s vs 10,000 ms
    if n["unit"] == "ms":
        readings.append((v / 1000, half / 1000))
    if n["unit"] in _MINUTES:
        readings.append((v * 60, half * 60))  # 60 min vs 3600 s
    return any(abs(r - e) <= tol + 1e-9 for r, tol in readings for e in pool)


def _check_text_numbers(text: str, where: str, items: list[EvidenceItem], evidence: list[EvidenceItem],
                        statuses: set[float]) -> list[Finding]:
    cfg = get_check_settings()["numbers"]
    allowed = {float(x) for x in cfg["always_allowed"]}
    pool, pool_text = _pool(items)
    findings = []
    # Evidence ids and routes carry digits that are names, not numbers: remove them first.
    for item in sorted(evidence, key=lambda e: -len(e.id)):
        text = text.replace(item.id, " ")
    text = _ROUTE_RE.sub(" ", text)
    for pattern in (_DATE_RE, _TIME_RE):
        for m in pattern.finditer(text):
            if m.group(0) not in pool_text:
                findings.append(_block("NUMBER_NOT_IN_EVIDENCE", f"{m.group(0)} is not in the cited evidence", where))
        text = pattern.sub(" ", text)
    for n in _numbers(text):
        if n["value"] in allowed and not n["pct"]:
            continue
        if n["value"] in statuses and n["decimals"] == 0 and not n["pct"] and not n["unit"]:
            continue
        if not _matches(n, pool):
            findings.append(_block("NUMBER_NOT_IN_EVIDENCE", f"{n['text']} is not in the cited evidence", where))
    return findings


def check_numbers(report: Report, evidence: list[EvidenceItem]) -> list[Finding]:
    """Summary: any evidence. Explanation: the cause's cited items. Why: the step's cited items
    (any evidence if the step cites nothing)."""
    by_id = _by_id(evidence)
    statuses = _status_codes(evidence)

    def cited(ids: Iterable[str]) -> list[EvidenceItem]:
        items = [by_id[i] for i in dict.fromkeys(ids) if i in by_id]
        return items

    findings = _check_text_numbers(report.summary, "summary", evidence, evidence, statuses)
    for i, cause in enumerate(report.causes):
        items = cited(c.evidence_id for c in cause.supporting + cause.contradicting)
        findings += _check_text_numbers(cause.explanation, f"causes[{i}].explanation", items, evidence, statuses)
    for i, step in enumerate(report.verification_steps):
        items = cited(step.cites) if step.cites else evidence
        findings += _check_text_numbers(step.why, f"verification_steps[{i}].why", items, evidence, statuses)
    return findings


# ---------- certainty ----------

def _phrase_re(phrase: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in phrase.lower().split())
    return re.compile(r"(?<!\w)" + words + r"(?!\w)")


def _is_negated(text: str, start: int, end: int) -> bool:
    cfg = get_check_settings()["certainty"]
    negations = set(cfg["negations"])
    before = re.findall(r"[\w']+", text[:start])[-cfg["words_before"]:]
    after = re.findall(r"[\w']+", text[end:])[:cfg["words_after"]]
    return any(w in negations for w in before + after)


def check_certainty(report: Report) -> list[Finding]:
    phrases = get_check_settings()["certainty"]["phrases"]
    fields = [("summary", report.summary)]
    for i, cause in enumerate(report.causes):
        fields += [(f"causes[{i}].cause", cause.cause), (f"causes[{i}].explanation", cause.explanation)]
    findings = []
    for where, text in fields:
        low = _norm(text)
        for phrase in phrases:
            for m in _phrase_re(phrase).finditer(low):
                if not _is_negated(low, m.start(), m.end()):
                    findings.append(_block("CERTAINTY", f"says {phrase!r}: causes are only likely or probable",
                                           where))
    return findings


# ---------- safe steps ----------

def check_safe_steps(report: Report) -> list[Finding]:
    """Only the step's action is checked: `why` may explain what a later fix would be."""
    findings = []
    for i, step in enumerate(report.verification_steps):
        low = _norm(step.action)
        for verb in get_check_settings()["safe_steps"]["verbs"]:
            words = r"\s+".join(re.escape(w) for w in verb.split())
            # restart, restarts, restarted, restarting
            if re.search(r"(?<!\w)" + words + r"(?:s|es|ed|d|ing)?(?!\w)", low):
                findings.append(_block("UNSAFE_STEP", f"{verb!r} changes the system: move to escalation",
                                       f"verification_steps[{i}].action"))
                break
    return findings


# ---------- secrets ----------

def _strings(value: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")


def check_secrets(report: Report) -> list[Finding]:
    """Every string in the report goes through redact.find_leaks. Only the kind is reported."""
    return [_block("SECRET", f"contains a secret ({', '.join(kinds)})", where)
            for where, text in _strings(report.model_dump(), "")
            if (kinds := find_leaks(text))]


# ---------- consistency ----------

def check_consistency(report: Report) -> list[Finding]:
    findings = []
    if report.outcome == "CLARIFY" and not report.missing_info:
        findings.append(_block("CLARIFY_NO_MISSING_INFO", "CLARIFY must say what information is missing",
                               "missing_info"))
    if report.outcome == "ESCALATE" and not report.escalation.needed:
        findings.append(_block("ESCALATE_NOT_NEEDED", "ESCALATE must set escalation.needed", "escalation"))
    return findings


# ---------- all checks ----------

def check_report(report: Report, evidence: list[EvidenceItem], allowed_causes: list[str]) -> list[Finding]:
    return (check_citations(report, evidence) + check_known_causes(report, allowed_causes)
            + check_numbers(report, evidence) + check_certainty(report) + check_safe_steps(report)
            + check_secrets(report) + check_consistency(report))


# ---------- remove blocked parts ----------

_PATH_RE = re.compile(r"^(?P<field>\w+)(?:\[(?P<i>\d+)\])?(?:\.(?P<sub>\w+)(?:\[(?P<j>\d+)\])?)?")


def apply_findings(report: Report, findings: list[Finding]) -> Report:
    """Return a copy of the report without the blocked parts (the input is not changed).

    - a blocked citation is dropped; a cause left with no supporting citation is dropped
    - a cause blocked anywhere else (unknown cause, certainty, numbers, secret) is dropped
    - a blocked step is dropped; a step's unknown cite id is dropped
    - a blocked summary / escalation reason is replaced by a plain line from checks.yaml
    - a blocked missing_info line is dropped
    - no cause left -> outcome CLARIFY (with a missing_info line if there is none)
    Run check_report again afterwards: anything still blocking means the report is not shown.
    """
    fallback = get_check_settings()["fallback"]
    r = report.model_copy(deep=True)
    drop_causes: set[int] = set()
    drop_cites: set[tuple[int, str, int]] = set()
    drop_steps: set[int] = set()
    drop_step_cites: set[tuple[int, int]] = set()
    drop_missing: set[int] = set()

    for f in findings:
        if f.severity != "block":
            continue
        m = _PATH_RE.match(f.where)
        if not m:
            continue
        field, sub = m.group("field"), m.group("sub")
        i = int(m.group("i")) if m.group("i") is not None else None
        j = int(m.group("j")) if m.group("j") is not None else None
        if field == "summary":
            r.summary = fallback["summary"]
        elif field == "escalation" and sub == "reason":
            r.escalation.reason = fallback["escalation_reason"]
        elif field == "escalation" and sub == "team":
            r.escalation.team = ""
        elif field == "missing_info" and i is not None:
            drop_missing.add(i)
        elif field == "causes" and i is not None:
            if sub in ("supporting", "contradicting") and j is not None:
                drop_cites.add((i, sub, j))
            else:
                drop_causes.add(i)
        elif field == "verification_steps" and i is not None:
            if sub == "cites" and j is not None:
                drop_step_cites.add((i, j))
            else:
                drop_steps.add(i)

    causes = []
    for i, cause in enumerate(r.causes):
        if i in drop_causes:
            continue
        cause.supporting = [c for j, c in enumerate(cause.supporting) if (i, "supporting", j) not in drop_cites]
        cause.contradicting = [c for j, c in enumerate(cause.contradicting)
                               if (i, "contradicting", j) not in drop_cites]
        if cause.supporting:
            causes.append(cause)
    r.causes = causes

    steps = []
    for i, step in enumerate(r.verification_steps):
        if i in drop_steps:
            continue
        step.cites = [c for j, c in enumerate(step.cites) if (i, j) not in drop_step_cites]
        steps.append(step)
    r.verification_steps = steps
    r.missing_info = [m for i, m in enumerate(r.missing_info) if i not in drop_missing]

    if not r.causes:
        r.outcome = "CLARIFY"
        if not r.missing_info:
            r.missing_info = [fallback["missing_info"]]
    return r

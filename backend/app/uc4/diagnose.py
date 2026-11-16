"""The full UC4 pipeline the API calls: diagnose(case_id or Case) -> Diagnosis (JSON-ready).

  load case -> collect_evidence -> get_signals -> [classifier, 2nd opinion] -> rank_causes -> decide
  -> report (LLM write_report if present, else the code template) -> checks (check_report, apply_findings)

Every step is timed into Diagnosis.trace. Teammates' pieces are optional: if the classifier or
write_report is missing (or raises), a trace note says so and the pipeline carries on.
Labels (expected_*, missing_info, generation...) are never read here.
"""
import importlib
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from app.uc4.checks import apply_findings, check_report, groundedness
from app.uc4.evidence import collect_evidence
from app.uc4.gate import decide
from app.uc4.models import Case, Diagnosis, EvidenceItem, GateDecision, RankedCause, TraceStep
from app.uc4.rank import rank_causes
from app.uc4.signals import get_signals
from app.uc4.store import get_case
from app.uc4.template_report import build_report

# Where teammates' pieces are expected (contract written in docs/PLAN.md).
CLASSIFIER = ("app.uc4.ml.classifier", "predict_class")  # predict_class(line: str) -> class | (class, prob)
REPORT_WRITER = ("app.uc4.report", "write_report")  # write_report(case, ranked, decision, evidence) -> Report


# ---------- the code-only steps (used by tune_rank.py, eval_rank.py and tests) ----------

@dataclass
class CodeRun:
    case: Case
    evidence: list[EvidenceItem]
    signals: dict[str, Optional[bool]]
    ranked: list[RankedCause]
    decision: GateDecision


def run_code_steps(case: Case) -> CodeRun:
    """evidence -> signals -> rank -> gate, no report and no timing."""
    evidence = collect_evidence(case)
    signals = get_signals(case)
    ranked = rank_causes(signals, evidence)
    return CodeRun(case, evidence, signals, ranked, decide(ranked, signals, evidence))


# ---------- helpers ----------

class _Trace:
    def __init__(self) -> None:
        self.steps: list[TraceStep] = []

    @contextmanager
    def step(self, name: str):
        """Time a block; the block may set note["detail"]."""
        note = {"detail": ""}
        start = time.perf_counter()
        try:
            yield note
        finally:
            ms = round((time.perf_counter() - start) * 1000, 2)
            self.steps.append(TraceStep(step=name, ms=ms, detail=note["detail"]))


def _optional(module: str, name: str) -> Optional[Callable[..., Any]]:
    """A teammate's function if its module exists, else None."""
    try:
        return getattr(importlib.import_module(module), name, None)
    except ImportError:
        return None


def _classifier_line(evidence: list[EvidenceItem]) -> Optional[str]:
    """The focal request in the classifier's training format: status=.. route=.. code=.. message=.."""
    for item in evidence:
        if item.kind == "request":
            d = item.data
            return (f"status={d.get('status')} route={d.get('route')} code={d.get('error_code') or ''} "
                    f"message={d.get('error_message') or ''}")
    return None


# ---------- the full pipeline ----------

def diagnose(case_or_id: Union[str, Case]) -> Diagnosis:
    """Run every step for one case and return the Diagnosis the API sends."""
    trace = _Trace()

    with trace.step("load_case") as t:
        case = get_case(case_or_id) if isinstance(case_or_id, str) else case_or_id
        t["detail"] = f"{case.case_id} {case.route}"

    with trace.step("collect_evidence") as t:
        evidence = collect_evidence(case)
        missing = sum(1 for e in evidence if e.kind == "missing")
        t["detail"] = f"{len(evidence)} items, {missing} missing"

    with trace.step("get_signals") as t:
        signals = get_signals(case)
        t["detail"] = f"{sum(1 for v in signals.values() if v)} of {len(signals)} signals on"

    with trace.step("classifier") as t:
        predict = _optional(*CLASSIFIER)
        line = _classifier_line(evidence)
        if predict is None:
            t["detail"] = f"skipped: {CLASSIFIER[0]}.{CLASSIFIER[1]} not available yet"
        elif line is None:
            t["detail"] = "skipped: no focal request to classify"
        else:
            try:
                out = predict(line)
                label, prob = (out if isinstance(out, tuple) else (out, None))
                t["detail"] = f"second opinion: class {label}" + (f" ({float(prob):.2f})" if prob is not None else "")
            except Exception as exc:  # a teammate's piece must never break the pipeline
                t["detail"] = f"skipped: classifier failed ({type(exc).__name__})"

    with trace.step("rank_causes") as t:
        ranked = rank_causes(signals, evidence)
        t["detail"] = f"{len(ranked)} causes ranked"

    with trace.step("decide") as t:
        decision = decide(ranked, signals, evidence)
        t["detail"] = decision.outcome + (" + escalate" if decision.escalate else "") + (
            f", {len(decision.alternatives)} alternatives" if decision.alternatives else "")

    with trace.step("report") as t:
        generator = "template"
        report = None
        writer = _optional(*REPORT_WRITER)
        if writer is not None:
            try:
                report = writer(case, ranked, decision, evidence)
                generator = "llm"
                t["detail"] = f"written by {REPORT_WRITER[0]}.{REPORT_WRITER[1]}"
            except Exception as exc:
                t["detail"] = f"write_report failed ({type(exc).__name__}); used the code template"
        else:
            t["detail"] = f"{REPORT_WRITER[0]}.{REPORT_WRITER[1]} not available yet; used the code template"
        if report is None:
            report = build_report(case, ranked, decision, evidence)

    with trace.step("checks") as t:
        allowed = [r.cause for r in ranked]
        findings = check_report(report, evidence, allowed)
        cited = any(c.supporting or c.contradicting for c in report.causes)
        grounded = groundedness(report, evidence) if cited else None  # nothing to cite -> None, not 0.0
        shown = apply_findings(report, findings)
        blocking = sum(1 for f in findings if f.severity == "block")
        t["detail"] = f"{len(findings)} findings ({blocking} blocking), groundedness " + (f"{grounded:.2f}" if grounded is not None else "n/a (nothing cited)")

    # On CLARIFY no cause is claimed anywhere (the report, if checks emptied it, is CLARIFY too).
    outcome = "CLARIFY" if decision.outcome == "CLARIFY" or shown.outcome == "CLARIFY" else "RECOMMEND"
    claim = outcome == "RECOMMEND"
    top = ranked[0] if (ranked and claim) else None
    return Diagnosis(
        case_id=case.case_id, route=case.route, onset_ts=case.onset_ts,
        outcome=outcome, escalate=decision.escalate and claim,
        failure_class=top.failure_class if top else None,
        class_confidence=round(sum(r.confidence for r in ranked if r.failure_class == top.failure_class), 6)
        if top else None,
        ranked=ranked if claim else [],
        alternatives=decision.alternatives if claim else [],
        tell_apart=decision.tell_apart if claim else None,
        evidence=evidence,
        missing_info=list(shown.missing_info) if outcome == "CLARIFY" else list(decision.missing_info),
        report=shown, report_findings=findings, groundedness=None if grounded is None else round(grounded, 4), generator=generator,
        trace=trace.steps,
    )

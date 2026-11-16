"""Run the full pipeline for one case and print a readable diagnosis (or the JSON the API returns).

Usage (from backend):  .\\.venv\\Scripts\\python.exe scripts\\diagnose_case.py UC4-0050 [--json]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.uc4.diagnose import diagnose  # noqa: E402
from app.uc4.models import Diagnosis  # noqa: E402


def show(d: Diagnosis) -> None:
    print(f"{d.case_id}  {d.route}  onset {d.onset_ts:%Y-%m-%d %H:%M:%S} UTC")
    head = f"Outcome: {d.outcome}" + ("  (ESCALATE: privileged first check)" if d.escalate else "")
    print(head + f"   generator: {d.generator}   groundedness: {d.groundedness}")
    if d.failure_class:
        print(f"Class: {d.failure_class} (confidence {d.class_confidence:.2f})")

    if d.ranked:
        print("\nTop causes:")
        for r in d.ranked[:3]:
            tie = "  near-tie" if r.near_tie else ""
            print(f"  {r.rank}. {r.cause:<28} {r.confidence:.2f}  {r.status}{tie}  first check: {r.first_check}")
    if d.tell_apart:
        print(f"\n{d.tell_apart.note}")

    r = d.report
    if r:
        print(f"\nReport ({r.outcome}): {r.summary}")
        for c in r.causes:
            print(f"  - {c.cause} [{c.likelihood}]: {c.explanation}")
            for cite in c.supporting:
                print(f"      for     [{cite.evidence_id}]")
            for cite in c.contradicting:
                print(f"      against [{cite.evidence_id}]")
        print("  Verification steps (read-only):")
        for s in r.verification_steps:
            print(f"    * {s.action}  -- {s.why}")
        if r.escalation.needed:
            print(f"  Escalation to {r.escalation.team}: {r.escalation.reason}")
        if r.missing_info:
            print("  Missing info:")
            for m in r.missing_info:
                print(f"    * {m}")
    blocking = [f for f in d.report_findings if f.severity == "block"]
    print(f"\nChecks: {len(d.report_findings)} findings, {len(blocking)} blocking")
    for f in d.report_findings:
        print(f"  {f.severity} {f.code} at {f.where}: {f.message}")

    print("\nEvidence:")
    for e in d.evidence:
        print(f"  [{e.id}] {e.text}")
    print("\nTrace:")
    for t in d.trace:
        print(f"  {t.step:<17} {t.ms:>8.2f} ms  {t.detail}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    try:
        d = diagnose(args[0])
    except KeyError as exc:
        print(exc.args[0])
        return 1
    if "--json" in argv:
        print(d.model_dump_json(indent=2))
    else:
        show(d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

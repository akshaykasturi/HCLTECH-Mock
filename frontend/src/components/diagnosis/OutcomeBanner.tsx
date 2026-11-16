import { CircleDashed, ShieldAlert, Sparkles } from "lucide-react";
import { formatConfidence, humanize } from "../../lib/format";
import { sortedCauses } from "../../lib/evidence";
import type { Diagnosis } from "../../lib/types";
import { CauseStatusBadge, EscalateBadge, OutcomeBadge } from "../common/status";

/** The headline: RECOMMEND (with the top likely cause) or CLARIFY (what is missing). Escalation is a flag, not an outcome. */
export function OutcomeBanner({ diagnosis }: { diagnosis: Diagnosis }) {
  const top = sortedCauses(diagnosis)[0];
  if (diagnosis.outcome === "CLARIFY") {
    return (
      <section aria-labelledby="outcome-title" className="rounded-xl border border-warning/40 bg-warning-soft p-5">
        <div className="flex flex-wrap items-center gap-2">
          <CircleDashed className="h-5 w-5 text-warning-text" aria-hidden />
          <h2 id="outcome-title" className="text-lg font-semibold text-ink">More information needed</h2>
          <OutcomeBadge outcome="CLARIFY" />
          {diagnosis.escalate && <EscalateBadge />}
        </div>
        <p className="mt-2 text-sm text-slate-700">
          The evidence is not enough to name a likely cause, so no cause is claimed.
          {diagnosis.missing_info.length > 0
            ? ` Provide the ${diagnosis.missing_info.length === 1 ? "item" : `${diagnosis.missing_info.length} items`} listed under Missing information and run the diagnosis again.`
            : " The backend did not list specific missing items."}
        </p>
      </section>
    );
  }
  return (
    <section aria-labelledby="outcome-title"
             className={`rounded-xl border p-5 ${diagnosis.escalate ? "border-danger/40 bg-danger-soft" : "border-primary/30 bg-primary-soft"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="h-5 w-5 text-primary" aria-hidden />
        <h2 id="outcome-title" className="text-lg font-semibold text-ink">Recommendation</h2>
        <OutcomeBadge outcome="RECOMMEND" />
        {diagnosis.escalate && <EscalateBadge />}
      </div>
      {top ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <p>
            <span className="text-muted">Most likely cause: </span>
            <span className="font-semibold text-ink">{humanize(top.cause)}</span>{" "}
            <code className="font-mono text-xs text-slate-600">({top.cause})</code>
          </p>
          <CauseStatusBadge status={top.status} />
          <p><span className="text-muted">Confidence </span><span className="font-mono">{formatConfidence(top.confidence)}</span></p>
          {diagnosis.failure_class && (
            <p>
              <span className="text-muted">Failure class </span>
              <span className="font-medium">{humanize(diagnosis.failure_class)}</span>
              <span className="font-mono text-slate-600"> ({formatConfidence(diagnosis.class_confidence)})</span>
            </p>
          )}
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-700">The backend returned no ranked causes.</p>
      )}
      <p className="mt-3 text-xs text-slate-600">
        A likely cause is not confirmed: a reviewer confirms it by running the first check. Confidence is the model's estimate, not certainty.
      </p>
      {diagnosis.escalate && (
        <p className="mt-2 flex items-start gap-2 text-sm font-medium text-danger-text">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Escalate: the first check needs privileged access. A person with that access should run it and decide any fix.
        </p>
      )}
    </section>
  );
}

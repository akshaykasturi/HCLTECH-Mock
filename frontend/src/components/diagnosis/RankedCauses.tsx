import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ListOrdered, ShieldAlert, Terminal } from "lucide-react";
import { evidenceIndex, resolveIds, sortedCauses } from "../../lib/evidence";
import { formatRatio, humanize } from "../../lib/format";
import type { Diagnosis, EvidenceItem, RankedCause, SignalLink } from "../../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState } from "../common/ui";
import { CauseStatusBadge, ConfidenceBar } from "../common/status";
import { EvidenceRef } from "../evidence/EvidenceBits";

const INITIAL_VISIBLE = 5;

function SignalList({ title, links, index, diagnosisId, tone }:
  { title: string; links: SignalLink[]; index: Map<string, EvidenceItem>; diagnosisId: string; tone: "support" | "contra" }) {
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{title}</h4>
      {links.length === 0 ? <p className="text-sm text-muted">None.</p> : (
        <ul className="space-y-2">
          {links.map((link, i) => (
            <li key={`${link.signal}-${i}`} className="rounded-lg border border-slate-100 bg-slate-50/60 p-2.5 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <code className="font-mono text-xs font-medium text-ink">{link.signal}</code>
                <Badge tone={link.present ? "neutral" : "warning"}>{link.present ? "seen" : "expected but absent"}</Badge>
                <span className={`font-mono text-xs ${tone === "support" ? "text-success-text" : "text-danger-text"}`}
                      title="How much this signal's value favours this cause compared with the others (> 1 favours it)">
                  {formatRatio(link.ratio)}
                </span>
              </div>
              {link.evidence_ids.length > 0 ? (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {resolveIds(link.evidence_ids, index).map((ref) => (
                    <EvidenceRef key={ref.id} id={ref.id} item={ref.item} diagnosisId={diagnosisId} />
                  ))}
                </div>
              ) : <p className="mt-1 text-xs text-muted">No evidence item linked to this signal.</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CauseCard({ cause, index, diagnosisId }: { cause: RankedCause; index: Map<string, EvidenceItem>; diagnosisId: string }) {
  const [open, setOpen] = useState(false);
  const panelId = `cause-${cause.rank}-details`;
  return (
    <li className="rounded-lg border border-slate-200 p-4" aria-label={`Rank ${cause.rank}: ${cause.cause}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">
            {cause.rank}
          </span>
          <div className="min-w-0">
            <p className="font-medium text-ink">{humanize(cause.cause)}</p>
            <p className="text-xs text-muted">
              <code className="font-mono">{cause.cause}</code> · {humanize(cause.failure_class)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CauseStatusBadge status={cause.status} />
          {cause.near_tie && <Badge tone="warning" title="Within the margin of the top cause">Near tie</Badge>}
          {cause.escalate && <Badge tone="danger" icon={<ShieldAlert className="h-3.5 w-3.5" aria-hidden />}>Privileged check</Badge>}
          <ConfidenceBar value={cause.confidence} label={`Confidence for ${cause.cause}`} />
        </div>
      </div>
      {cause.first_check && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
          <Terminal className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden />
          <span><span className="font-medium">First check: </span><code className="font-mono text-xs">{cause.first_check}</code></span>
        </p>
      )}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls={panelId}
              className="mt-3 inline-flex items-center gap-1 rounded text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
        {open ? <ChevronUp className="h-4 w-4" aria-hidden /> : <ChevronDown className="h-4 w-4" aria-hidden />}
        {open ? "Hide signals" : `Show signals (${cause.supporting.length} for, ${cause.contradicting.length} against)`}
      </button>
      {open && (
        <div id={panelId} className="mt-3 grid gap-4 md:grid-cols-2">
          <SignalList title="Supporting" links={cause.supporting} index={index} diagnosisId={diagnosisId} tone="support" />
          <SignalList title="Contradicting" links={cause.contradicting} index={index} diagnosisId={diagnosisId} tone="contra" />
          {cause.missing_info.length > 0 && (
            <div className="md:col-span-2">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Missing for this cause</h4>
              <ul className="list-inside list-disc text-sm">{cause.missing_info.map((m) => <li key={m}>{m}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function RankedCauses({ diagnosis }: { diagnosis: Diagnosis }) {
  const causes = useMemo(() => sortedCauses(diagnosis), [diagnosis]);
  const index = useMemo(() => evidenceIndex(diagnosis), [diagnosis]);
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? causes : causes.slice(0, INITIAL_VISIBLE);
  return (
    <Card aria-labelledby="ranked-title">
      <CardHeader id="ranked-title" icon={<ListOrdered className="h-5 w-5" />} title="Ranked causes"
                  description="Ordered by rank. Status and confidence come from the pipeline; none is confirmed." />
      {causes.length === 0 ? (
        <EmptyState title="No ranked causes">
          {diagnosis.outcome === "CLARIFY"
            ? "A CLARIFY diagnosis claims no cause until the missing information is provided."
            : "The backend returned no ranked causes for this diagnosis."}
        </EmptyState>
      ) : (
        <div className="p-5">
          <ol className="space-y-3">
            {visible.map((c) => <CauseCard key={`${c.rank}-${c.cause}`} cause={c} index={index} diagnosisId={diagnosis.diagnosis_id} />)}
          </ol>
          {causes.length > INITIAL_VISIBLE && (
            <Button variant="ghost" className="mt-3" onClick={() => setShowAll((s) => !s)} aria-expanded={showAll}>
              {showAll ? "Show top 5 only" : `Show all ${causes.length} causes`}
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}

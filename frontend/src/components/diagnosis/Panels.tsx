import { useMemo, useState } from "react";
import { BadgeCheck, ChevronDown, ChevronUp, FileText, GitCompare, ListChecks, Route, ShieldAlert, ShieldCheck } from "lucide-react";
import { evidenceIndex, resolveIds } from "../../lib/evidence";
import { formatConfidence, formatMs, generatorLabel, humanize } from "../../lib/format";
import type { Citation, Diagnosis, EvidenceItem } from "../../lib/types";
import { Badge, Card, CardHeader, EmptyState } from "../common/ui";
import { EvidenceRef } from "../evidence/EvidenceBits";

// ---------- Missing information ----------

export function MissingInfo({ diagnosis, prominent = false }: { diagnosis: Diagnosis; prominent?: boolean }) {
  const items = diagnosis.missing_info;
  return (
    <Card aria-labelledby="missing-title" className={prominent ? "border-warning/50" : ""}>
      <CardHeader id="missing-title" icon={<ListChecks className="h-5 w-5" />} title="Missing information"
                  description={prominent ? "Provide these to get a recommendation." : undefined} />
      {items.length === 0 ? (
        <p className="px-5 py-4 text-sm text-muted">Nothing reported missing.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {items.map((m) => (
            <li key={m} className="flex items-start gap-2 px-5 py-3 text-sm">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning" aria-hidden />{m}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------- Close call ----------

export function CloseCall({ diagnosis }: { diagnosis: Diagnosis }) {
  const tell = diagnosis.tell_apart;
  const competing = tell?.causes?.length ? tell.causes : diagnosis.alternatives;
  if (!tell && diagnosis.alternatives.length < 2) return null;
  return (
    <Card aria-labelledby="closecall-title" className="border-warning/40">
      <CardHeader id="closecall-title" icon={<GitCompare className="h-5 w-5" />} title="Close call: how to tell them apart"
                  description="These causes are within the margin of each other. Run the checks below to separate them." />
      <div className="space-y-4 p-5 text-sm">
        <div className="flex flex-wrap gap-2" aria-label="Competing causes">
          {competing.map((c) => <Badge key={c} tone="warning">{humanize(c)}</Badge>)}
        </div>
        {tell?.note && <p className="text-slate-700">{tell.note}</p>}
        {tell && Object.keys(tell.first_checks ?? {}).length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Recommended checks</h3>
            <ul className="space-y-1.5">
              {Object.entries(tell.first_checks).map(([cause, check]) => (
                <li key={cause} className="flex flex-wrap gap-2">
                  <span className="font-medium">{humanize(cause)}:</span>
                  {check ? <code className="font-mono text-xs">{check}</code> : <span className="text-muted">no first check listed</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {tell && (tell.signals?.length ?? 0) > 0 && (
          <div className="overflow-x-auto">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Distinguishing signals</h3>
            <table className="w-full min-w-[28rem] text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th scope="col" className="py-1.5 pr-3 font-medium">Signal</th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">Favours</th>
                  {competing.map((c) => <th key={c} scope="col" className="py-1.5 pr-3 font-medium">P(on | {humanize(c)})</th>)}
                  <th scope="col" className="py-1.5 font-medium">In this case</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {tell.signals.map((s) => (
                  <tr key={s.signal}>
                    <td className="py-1.5 pr-3"><code className="font-mono text-xs">{s.signal}</code></td>
                    <td className="py-1.5 pr-3">{humanize(s.favours)}</td>
                    {competing.map((c) => <td key={c} className="py-1.5 pr-3 font-mono text-xs">{formatConfidence(s.p_on?.[c])}</td>)}
                    <td className="py-1.5">{s.observed === true ? "Seen" : s.observed === false ? "Not seen" : "Unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

// ---------- Report ----------

function Citations({ items, index, diagnosisId }: { items: Citation[]; index: Map<string, EvidenceItem>; diagnosisId: string }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 space-y-2">
      {items.map((c, i) => (
        <li key={`${c.evidence_id}-${i}`} className="border-l-2 border-slate-200 pl-3">
          <EvidenceRef id={c.evidence_id} item={index.get(c.evidence_id) ?? null} diagnosisId={diagnosisId} />
          <blockquote className="mt-1 text-sm italic text-slate-600">“{c.quote}”</blockquote>
        </li>
      ))}
    </ul>
  );
}

export function ReportPanel({ diagnosis }: { diagnosis: Diagnosis }) {
  const index = useMemo(() => evidenceIndex(diagnosis), [diagnosis]);
  const report = diagnosis.report;
  const id = diagnosis.diagnosis_id;
  return (
    <Card aria-labelledby="report-title">
      <CardHeader id="report-title" icon={<FileText className="h-5 w-5" />} title="Report"
                  description={report ? "Checked by code before it is shown; citations link to the evidence." : undefined}
                  actions={<Badge tone="neutral" title="Which generator wrote the report text">{generatorLabel(diagnosis.generator)}</Badge>} />
      {!report ? (
        <EmptyState title="No report for this diagnosis">The backend returned no report text, so none is shown.</EmptyState>
      ) : (
        <div className="space-y-6 p-5 text-sm">
          <section aria-label="Summary">
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Summary</h3>
            <p className="text-ink">{report.summary}</p>
          </section>

          {report.causes.length > 0 && (
            <section aria-label="Cause explanations">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Cause explanations</h3>
              <ul className="space-y-4">
                {report.causes.map((c) => (
                  <li key={c.cause}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{humanize(c.cause)}</span>
                      <Badge tone={c.likelihood === "likely" ? "primary" : "warning"}>{humanize(c.likelihood)}</Badge>
                    </div>
                    <p className="mt-1 text-slate-700">{c.explanation}</p>
                    {c.supporting.length > 0 && <p className="mt-2 text-xs font-medium text-muted">Supporting evidence</p>}
                    <Citations items={c.supporting} index={index} diagnosisId={id} />
                    {c.contradicting.length > 0 && <p className="mt-2 text-xs font-medium text-muted">Contradicting evidence</p>}
                    <Citations items={c.contradicting} index={index} diagnosisId={id} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-label="Verification steps">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Verification steps</h3>
            {report.verification_steps.length === 0 ? <p className="text-muted">No verification steps.</p> : (
              <ol className="space-y-3">
                {report.verification_steps.map((s, i) => (
                  <li key={`${s.action}-${i}`} className="flex gap-3">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary-soft text-xs font-semibold text-primary">{i + 1}</span>
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{s.action}</p>
                      <p className="text-slate-600">{s.why}</p>
                      {s.cites.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {resolveIds(s.cites, index).map((r) => <EvidenceRef key={r.id} id={r.id} item={r.item} diagnosisId={id} />)}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {report.escalation && (
            <section aria-label="Escalation"
                     className={`rounded-lg border p-3 ${report.escalation.needed ? "border-danger/30 bg-danger-soft" : "border-slate-200 bg-slate-50"}`}>
              <h3 className="flex items-center gap-2 font-medium">
                {report.escalation.needed
                  ? <><ShieldAlert className="h-4 w-4 text-danger-text" aria-hidden />Escalation needed</>
                  : <><ShieldCheck className="h-4 w-4 text-success-text" aria-hidden />No escalation needed</>}
              </h3>
              {report.escalation.team && <p className="mt-1"><span className="text-muted">Team: </span>{report.escalation.team}</p>}
              {report.escalation.reason && <p className="mt-1 text-slate-700">{report.escalation.reason}</p>}
            </section>
          )}

          {report.missing_info.length > 0 && (
            <section aria-label="Report missing information">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Missing information</h3>
              <ul className="list-inside list-disc">{report.missing_info.map((m) => <li key={m}>{m}</li>)}</ul>
            </section>
          )}
        </div>
      )}
    </Card>
  );
}

// ---------- Checks: groundedness and findings ----------

export function ChecksPanel({ diagnosis }: { diagnosis: Diagnosis }) {
  const findings = diagnosis.report_findings;
  const tone = (s: string) => (s === "block" ? "danger" : s === "warn" ? "warning" : "neutral") as "danger" | "warning" | "neutral";
  return (
    <Card aria-labelledby="checks-title">
      <CardHeader id="checks-title" icon={<BadgeCheck className="h-5 w-5" />} title="Report checks" />
      <div className="space-y-3 p-5 text-sm">
        <p>
          <span className="text-muted">Groundedness: </span>
          {diagnosis.groundedness === null
            ? <span className="text-muted">not available</span>
            : <span className="font-mono" title="Verified citations divided by all citations">{formatConfidence(diagnosis.groundedness)}</span>}
        </p>
        {findings.length === 0 ? (
          <p className="text-muted">No issues found by the report checks.</p>
        ) : (
          <ul className="space-y-2">
            {findings.map((f, i) => (
              <li key={`${f.code}-${i}`} className="rounded-lg border border-slate-100 p-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={tone(f.severity)}>{f.severity}</Badge>
                  <code className="font-mono text-xs">{f.code}</code>
                  {f.where && <span className="text-xs text-muted">at {f.where}</span>}
                </div>
                <p className="mt-1 text-slate-700">{f.message}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

// ---------- Trace ----------

export function TracePanel({ diagnosis }: { diagnosis: Diagnosis }) {
  const [open, setOpen] = useState(false);
  const total = diagnosis.trace.reduce((sum, t) => sum + (Number.isFinite(t.ms) ? t.ms : 0), 0);
  return (
    <Card aria-labelledby="trace-title">
      <div className="flex items-center justify-between gap-3 px-5 py-4">
        <h2 id="trace-title" className="flex items-center gap-2 text-base font-semibold">
          <Route className="h-5 w-5 text-primary" aria-hidden />How this was decided
        </h2>
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="trace-body"
                className="inline-flex items-center gap-1 rounded text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
          {open ? <ChevronUp className="h-4 w-4" aria-hidden /> : <ChevronDown className="h-4 w-4" aria-hidden />}
          {open ? "Hide steps" : `Show ${diagnosis.trace.length} steps`}
        </button>
      </div>
      {open && (
        <div id="trace-body" className="border-t border-slate-100 px-5 pb-5">
          {diagnosis.trace.length === 0 ? <p className="pt-4 text-sm text-muted">The backend sent no trace.</p> : (
            <div className="overflow-x-auto">
              <table className="mt-3 w-full min-w-[30rem] text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Step</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">Time</th>
                    <th scope="col" className="py-1.5 font-medium">Detail</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {diagnosis.trace.map((t, i) => (
                    <tr key={`${t.step}-${i}`}>
                      <td className="py-1.5 pr-3"><code className="font-mono text-xs">{t.step}</code></td>
                      <td className="py-1.5 pr-3 text-right font-mono text-xs tabular-nums">{formatMs(t.ms)}</td>
                      <td className="py-1.5 text-slate-700">{t.detail || "—"}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="text-xs text-muted">
                    <td className="pt-2">Total</td><td className="pt-2 text-right font-mono">{formatMs(total)}</td><td />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

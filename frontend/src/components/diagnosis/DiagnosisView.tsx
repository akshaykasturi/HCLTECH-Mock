import { useMemo } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ClipboardCheck, FileSearch, Info, Link2 } from "lucide-react";
import { unresolvedIds } from "../../lib/evidence";
import { formatTimestamp, generatorLabel, splitRoute } from "../../lib/format";
import type { Diagnosis } from "../../lib/types";
import { Card, CardHeader, Mono } from "../common/ui";
import { OutcomeBanner } from "./OutcomeBanner";
import { RankedCauses } from "./RankedCauses";
import { ChecksPanel, CloseCall, MissingInfo, ReportPanel, TracePanel } from "./Panels";

const actionLink = "inline-flex w-full items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function DiagnosisMeta({ diagnosis }: { diagnosis: Diagnosis }) {
  const { method, path } = splitRoute(diagnosis.route);
  const id = encodeURIComponent(diagnosis.diagnosis_id);
  return (
    <Card aria-labelledby="meta-title">
      <CardHeader id="meta-title" icon={<Info className="h-5 w-5" />} title="Diagnosis details" />
      <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-2 px-5 py-4 text-sm">
        <dt className="text-muted">Case</dt>
        <dd><Link to={`/diagnosis/${encodeURIComponent(diagnosis.case_id)}`} className="font-mono text-primary hover:underline">{diagnosis.case_id}</Link></dd>
        <dt className="text-muted">Route</dt>
        <dd><Mono>{method && <span className="font-semibold">{method} </span>}{path}</Mono></dd>
        <dt className="text-muted">Onset</dt><dd>{formatTimestamp(diagnosis.onset_ts)}</dd>
        <dt className="text-muted">Diagnosed</dt><dd>{formatTimestamp(diagnosis.created_at)}</dd>
        <dt className="text-muted">Diagnosis ID</dt><dd><Mono>{diagnosis.diagnosis_id}</Mono></dd>
        <dt className="text-muted">Evidence</dt><dd>{diagnosis.evidence.length} items</dd>
        <dt className="text-muted">Report</dt><dd>{generatorLabel(diagnosis.generator)}</dd>
      </dl>
      <div className="grid gap-2 border-t border-slate-100 p-4">
        <Link to={`/review?d=${id}`} className={`${actionLink} bg-primary text-white hover:bg-primary-hover`}>
          <ClipboardCheck className="h-4 w-4" aria-hidden />Review this diagnosis
        </Link>
        <Link to={`/evidence?d=${id}`} className={`${actionLink} border border-slate-200 bg-white text-ink hover:bg-slate-50`}>
          <FileSearch className="h-4 w-4" aria-hidden />Open Evidence Explorer
        </Link>
        <Link to={`/diagnoses/${id}`} className={`${actionLink} text-ink hover:bg-slate-100`}>
          <Link2 className="h-4 w-4" aria-hidden />Permanent link
        </Link>
      </div>
    </Card>
  );
}

export function DiagnosisView({ diagnosis }: { diagnosis: Diagnosis }) {
  const unresolved = useMemo(() => unresolvedIds(diagnosis), [diagnosis]);
  const clarify = diagnosis.outcome === "CLARIFY";
  return (
    <div className="space-y-6">
      <OutcomeBanner diagnosis={diagnosis} />
      {unresolved.length > 0 && (
        <div role="note" className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-text" aria-hidden />
          <p>
            {unresolved.length === 1 ? "1 cited evidence id is" : `${unresolved.length} cited evidence ids are`} not in this
            diagnosis's evidence list: <span className="font-mono">{unresolved.join(", ")}</span>. They are shown with a warning, not invented.
          </p>
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          {clarify && <MissingInfo diagnosis={diagnosis} prominent />}
          <RankedCauses diagnosis={diagnosis} />
          <CloseCall diagnosis={diagnosis} />
          <ReportPanel diagnosis={diagnosis} />
          <TracePanel diagnosis={diagnosis} />
        </div>
        <div className="min-w-0 space-y-6">
          <DiagnosisMeta diagnosis={diagnosis} />
          {!clarify && <MissingInfo diagnosis={diagnosis} />}
          <ChecksPanel diagnosis={diagnosis} />
        </div>
      </div>
    </div>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTargetDiagnosis } from "../hooks/useTargetDiagnosis";
import { sortedCauses } from "../lib/evidence";
import { formatTimestamp, humanize } from "../lib/format";
import type { Diagnosis } from "../lib/types";
import { FeedbackForm, FeedbackHistory } from "../components/feedback/Feedback";
import { DiagnosisPicker } from "../components/diagnosis/DiagnosisPicker";
import { CauseStatusBadge, ConfidenceBar, EscalateBadge, OutcomeBadge } from "../components/common/status";
import { Card, CardHeader, ErrorAlert, LoadingBlock, Mono, PageHeader } from "../components/common/ui";

function ReviewSummary({ diagnosis }: { diagnosis: Diagnosis }) {
  const top = sortedCauses(diagnosis).slice(0, 3);
  return (
    <Card aria-labelledby="review-summary-title">
      <CardHeader id="review-summary-title" title="What you are reviewing"
                  actions={<Link to={`/diagnoses/${encodeURIComponent(diagnosis.diagnosis_id)}`} className="rounded text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">Open full diagnosis</Link>} />
      <div className="space-y-4 p-5 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono font-semibold">{diagnosis.case_id}</span>
          <OutcomeBadge outcome={diagnosis.outcome} />{diagnosis.escalate && <EscalateBadge />}
          <span className="text-xs text-muted">{formatTimestamp(diagnosis.created_at)}</span>
        </div>
        <p className="text-xs text-muted">Diagnosis ID <Mono>{diagnosis.diagnosis_id}</Mono></p>
        {top.length === 0 ? (
          <p className="text-muted">This diagnosis claims no cause{diagnosis.outcome === "CLARIFY" ? " (CLARIFY)" : ""}. Feedback applies to the whole diagnosis.</p>
        ) : (
          <ol className="space-y-2">
            {top.map((c) => (
              <li key={c.cause} className="flex flex-wrap items-center gap-2">
                <span className="w-5 text-muted">#{c.rank}</span>
                <span className="font-medium">{humanize(c.cause)}</span>
                <CauseStatusBadge status={c.status} />
                <ConfidenceBar value={c.confidence} label={`Confidence for ${c.cause}`} />
              </li>
            ))}
          </ol>
        )}
        {diagnosis.missing_info.length > 0 && (
          <div><p className="text-xs font-medium uppercase tracking-wide text-muted">Missing information</p>
            <ul className="mt-1 list-inside list-disc">{diagnosis.missing_info.map((m) => <li key={m}>{m}</li>)}</ul></div>
        )}
      </div>
    </Card>
  );
}

export function ReviewPage() {
  const { diagnosisId, diagnosis, loading, error, retry } = useTargetDiagnosis();
  const [refreshKey, setRefreshKey] = useState(0);
  const hrefFor = (id: string) => `/review?d=${encodeURIComponent(id)}`;
  return (
    <>
      <PageHeader title="Human Review"
                  description="A person confirms, rejects or annotates a diagnosis after running its first check. Only a reviewer can confirm a cause." />
      {!diagnosisId ? (
        <DiagnosisPicker title="Choose a diagnosis to review" hrefFor={hrefFor}>Feedback needs a saved diagnosis.</DiagnosisPicker>
      ) : diagnosis ? (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-3">
            <FeedbackForm diagnosis={diagnosis} onSaved={() => setRefreshKey((k) => k + 1)} />
            <FeedbackHistory diagnosisId={diagnosis.diagnosis_id} refreshKey={refreshKey} />
          </div>
          <div className="lg:col-span-2"><ReviewSummary diagnosis={diagnosis} /></div>
        </div>
      ) : error ? (
        <div className="space-y-6">
          <ErrorAlert error={error} onRetry={retry} retrying={loading} />
          <DiagnosisPicker title="Choose another diagnosis" hrefFor={hrefFor} />
        </div>
      ) : <Card as="div"><LoadingBlock label="Loading diagnosis" rows={6} /></Card>}
    </>
  );
}

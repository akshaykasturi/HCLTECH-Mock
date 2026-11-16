import { Link, useSearchParams } from "react-router-dom";
import { useTargetDiagnosis } from "../hooks/useTargetDiagnosis";
import { EvidenceExplorer } from "../components/evidence/EvidenceExplorer";
import { DiagnosisPicker } from "../components/diagnosis/DiagnosisPicker";
import { EscalateBadge, OutcomeBadge } from "../components/common/status";
import { Card, ErrorAlert, LoadingBlock, PageHeader } from "../components/common/ui";

export function EvidencePage() {
  const [params] = useSearchParams();
  const { diagnosisId, diagnosis, loading, error, retry } = useTargetDiagnosis();
  const hrefFor = (id: string) => `/evidence?d=${encodeURIComponent(id)}`;
  return (
    <>
      <PageHeader title="Evidence Explorer"
                  description="Every evidence item the pipeline collected for a diagnosis, with the causes it supports or contradicts."
                  eyebrow={diagnosis && (
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Link to={`/diagnoses/${encodeURIComponent(diagnosis.diagnosis_id)}`} className="font-mono font-medium text-primary hover:underline">{diagnosis.case_id}</Link>
                      <OutcomeBadge outcome={diagnosis.outcome} />{diagnosis.escalate && <EscalateBadge />}
                    </div>
                  )} />
      {!diagnosisId ? (
        <DiagnosisPicker title="Choose a diagnosis" hrefFor={hrefFor}>Evidence belongs to a diagnosis. Run one or open a saved one.</DiagnosisPicker>
      ) : diagnosis ? (
        <EvidenceExplorer diagnosis={diagnosis} focusId={params.get("focus")} />
      ) : error ? (
        <div className="space-y-6">
          <ErrorAlert error={error} onRetry={retry} retrying={loading} />
          <DiagnosisPicker title="Choose another diagnosis" hrefFor={hrefFor} />
        </div>
      ) : <Card as="div"><LoadingBlock label="Loading diagnosis evidence" rows={6} /></Card>}
    </>
  );
}

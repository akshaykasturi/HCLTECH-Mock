import { Link, useParams } from "react-router-dom";
import { RotateCw } from "lucide-react";
import { useDiagnosis } from "../state/AppData";
import { DiagnosisView } from "../components/diagnosis/DiagnosisView";
import { Card, ErrorAlert, LoadingBlock, PageHeader } from "../components/common/ui";

export function SavedDiagnosisPage() {
  const { diagnosisId = "" } = useParams();
  const { diagnosis, loading, error, retry } = useDiagnosis(diagnosisId);
  return (
    <>
      <PageHeader title={diagnosis ? `Diagnosis · ${diagnosis.case_id}` : "Saved diagnosis"}
                  description="Read from the audit log with GET /api/diagnoses/{id}. The pipeline is not run again."
                  actions={diagnosis && (
                    <Link to={`/diagnosis/${encodeURIComponent(diagnosis.case_id)}`}
                          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
                      <RotateCw className="h-4 w-4" aria-hidden />Open case workspace
                    </Link>
                  )} />
      {diagnosis ? <DiagnosisView diagnosis={diagnosis} /> :
       error ? <ErrorAlert error={error} onRetry={retry} retrying={loading} /> :
       <Card as="div"><LoadingBlock label="Loading diagnosis" rows={6} /></Card>}
    </>
  );
}

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, Play, RotateCw, Stethoscope } from "lucide-react";
import { ID_PATTERN } from "../lib/api";
import { formatTimestamp, splitRoute } from "../lib/format";
import type { Diagnosis } from "../lib/types";
import { useAppData, useCases } from "../state/AppData";
import { useToast } from "../state/Toasts";
import { DiagnosisView } from "../components/diagnosis/DiagnosisView";
import { DiagnosisPicker } from "../components/diagnosis/DiagnosisPicker";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorAlert, Mono, PageHeader, Skeleton } from "../components/common/ui";

function CaseChooser() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useCases();
  const [value, setValue] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value) navigate(`/diagnosis/${encodeURIComponent(value)}`);
  };
  return (
    <Card aria-labelledby="choose-title">
      <CardHeader id="choose-title" icon={<Stethoscope className="h-5 w-5" />} title="Choose a case to diagnose"
                  description="Or pick one in the Case Explorer, where you can search and filter." />
      <div className="p-5">
        {error ? <ErrorAlert error={error} onRetry={() => void reload()} retrying={loading} /> : (
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <div className="min-w-[16rem] flex-1">
              <label htmlFor="case-choice" className="mb-1.5 block text-sm font-medium">Case</label>
              <select id="case-choice" value={value} onChange={(e) => setValue(e.target.value)} disabled={!data}
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30">
                <option value="">{loading && !data ? "Loading cases…" : "Select a case"}</option>
                {(data ?? []).map((c) => <option key={c.id} value={c.id}>{c.id} · {c.route}</option>)}
              </select>
            </div>
            <Button type="submit" variant="primary" disabled={!value}>Open workspace</Button>
            <Link to="/cases" className="rounded px-1 py-2 text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">Open Case Explorer</Link>
          </form>
        )}
      </div>
    </Card>
  );
}

function Workspace({ caseId }: { caseId: string }) {
  const { api, diagnoses, recentDiagnosisIds, rememberDiagnosis } = useAppData();
  const { notify } = useToast();
  const cases = useCases();
  const caseInfo = cases.data?.find((c) => c.id === caseId);
  const validId = ID_PATTERN.test(caseId);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [current, setCurrent] = useState<Diagnosis | null>(null);
  const inFlight = useRef(false); // stops a second POST before React re-renders the disabled button
  const controller = useRef<AbortController | null>(null);

  // Latest diagnosis for this case received in this session (so coming back shows it again).
  const latest = recentDiagnosisIds.map((id) => diagnoses.get(id)).find((d) => d?.case_id === caseId) ?? null;
  const shown = current?.case_id === caseId ? current : latest;

  useEffect(() => {
    setCurrent(null);
    setError(null);
    setRunning(false);
    return () => {
      controller.current?.abort();
      inFlight.current = false;
    };
  }, [caseId]);

  async function run() {
    if (inFlight.current || !validId) return;
    inFlight.current = true;
    const ctl = new AbortController();
    controller.current = ctl;
    setRunning(true);
    setError(null);
    try {
      const diagnosis = await api.diagnose(caseId, ctl.signal);
      if (ctl.signal.aborted) return;
      rememberDiagnosis(diagnosis);
      setCurrent(diagnosis);
      notify(`Diagnosis saved for ${diagnosis.case_id}: ${diagnosis.outcome}${diagnosis.escalate ? " (escalate)" : ""}.`);
    } catch (e) {
      if (!ctl.signal.aborted) setError(e);
    } finally {
      if (controller.current === ctl) {
        inFlight.current = false;
        setRunning(false);
      }
    }
  }

  const { method, path } = splitRoute(caseInfo?.route ?? "");
  return (
    <>
      <PageHeader title={`Diagnosis workspace · ${caseId}`}
                  description="Runs the team's real diagnosis pipeline on this case through POST /api/diagnose. Nothing here is generated in the browser."
                  actions={
                    <Button variant="primary" onClick={() => void run()} loading={running} loadingText="Diagnosing…" disabled={!validId}
                            icon={shown ? <RotateCw className="h-4 w-4" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}>
                      {shown ? "Run again" : "Run diagnosis"}
                    </Button>
                  } />

      <Card as="div" className="mb-6 p-5">
        {cases.loading && !cases.data ? <Skeleton className="h-5 w-2/3" /> : caseInfo ? (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span className="font-mono text-base font-semibold">{caseInfo.id}</span>
            <Mono><span className="font-semibold">{method}</span> {path}</Mono>
            <span className="text-slate-700">{caseInfo.summary}</span>
            <Badge>{caseInfo.split}</Badge>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-warning-text">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            {!validId ? "This is not a valid case ID." : cases.data ? "This case is not in the backend's case list." : "Case details are unavailable."}
            <Link to="/cases" className="font-medium text-primary hover:underline">Choose another case</Link>
          </p>
        )}
      </Card>

      <div aria-live="polite" className="sr-only">{running ? `Diagnosing ${caseId}` : ""}</div>
      {running && (
        <div role="status" className="mb-6 rounded-lg border border-primary/20 bg-primary-soft p-4 text-sm text-ink">
          Collecting evidence, ranking causes and checking the report on the backend…
        </div>
      )}
      {error !== null && <div className="mb-6"><ErrorAlert error={error} onRetry={() => void run()} retrying={running} /></div>}

      {shown ? (
        <>
          <p className="mb-3 text-xs text-muted">
            Showing diagnosis <span className="font-mono">{shown.diagnosis_id}</span> from {formatTimestamp(shown.created_at)}.
          </p>
          <DiagnosisView diagnosis={shown} />
        </>
      ) : !running && error === null ? (
        <Card as="div">
          <EmptyState title="No diagnosis yet" icon={<Stethoscope className="h-5 w-5" />}>
            Press Run diagnosis (top right) to see the outcome, ranked causes, evidence and report for this case.
          </EmptyState>
        </Card>
      ) : null}
    </>
  );
}

export function DiagnosisPage() {
  const { caseId } = useParams();
  if (caseId) return <Workspace caseId={caseId} />;
  return (
    <>
      <PageHeader title="Diagnosis workspace" description="Choose a case to run the real diagnosis pipeline, or open a saved diagnosis." />
      <div className="space-y-6">
        <CaseChooser />
        <DiagnosisPicker title="Open a saved diagnosis" hrefFor={(id) => `/diagnoses/${encodeURIComponent(id)}`}>
          Saved diagnoses are read back with GET /api/diagnoses/&#123;id&#125;; the pipeline is not run again.
        </DiagnosisPicker>
      </div>
    </>
  );
}

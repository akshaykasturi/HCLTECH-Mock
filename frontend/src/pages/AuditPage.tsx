import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Fingerprint, Search, ShieldCheck, ShieldX, Timer } from "lucide-react";
import { ID_PATTERN } from "../lib/api";
import { formatClock, formatTimestamp, humanize, shortHash } from "../lib/format";
import { sortedCauses } from "../lib/evidence";
import type { ChainStatus, Diagnosis, FeedbackRecord } from "../lib/types";
import { useAppData } from "../state/AppData";
import { EscalateBadge, OutcomeBadge } from "../components/common/status";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorAlert, Mono, PageHeader } from "../components/common/ui";

function ChainCard() {
  const { api } = useAppData();
  const [result, setResult] = useState<ChainStatus | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const busy = useRef(false);

  async function verify() {
    if (busy.current) return;
    busy.current = true;
    setLoading(true);
    setError(null);
    try {
      setResult(await api.verifyAudit());
      setCheckedAt(new Date());
    } catch (e) {
      setError(e);
      setResult(null);
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }

  return (
    <Card aria-labelledby="chain-title">
      <CardHeader id="chain-title" icon={<Fingerprint className="h-5 w-5" />} title="Audit chain verification"
                  description="Recalculates every SHA-256 hash in the append-only audit log (GET /api/audit/verify)."
                  actions={<Button variant="primary" onClick={() => void verify()} loading={loading} loadingText="Verifying…"
                                   icon={<ShieldCheck className="h-4 w-4" aria-hidden />}>Verify chain</Button>} />
      <div className="p-5" aria-live="polite">
        {error ? <ErrorAlert error={error} onRetry={() => void verify()} retrying={loading} /> : !result ? (
          <p className="text-sm text-muted">Not checked yet. Press Verify chain.</p>
        ) : result.valid ? (
          <div className="flex items-start gap-3 rounded-lg border border-success/40 bg-success-soft p-4">
            <ShieldCheck className="mt-0.5 h-5 w-5 text-success-text" aria-hidden />
            <div className="text-sm">
              <p className="font-semibold text-success-text">Chain verified</p>
              <p className="mt-0.5 text-slate-700">{result.events_checked} events checked, no gaps or edits found.</p>
              <p className="mt-1 text-xs text-muted">Head hash <Mono>{shortHash(result.head_hash, 16)}</Mono>{checkedAt && ` · checked at ${formatClock(checkedAt)}`}</p>
            </div>
          </div>
        ) : (
          <div role="alert" className="flex items-start gap-3 rounded-lg border border-danger/40 bg-danger-soft p-4">
            <ShieldX className="mt-0.5 h-5 w-5 text-danger-text" aria-hidden />
            <div className="text-sm">
              <p className="font-semibold text-danger-text">Chain check failed</p>
              <p className="mt-0.5 text-slate-700">
                {result.first_bad_seq !== null ? `At event #${result.first_bad_seq}: ` : ""}{result.reason ?? "unknown reason"}
              </p>
              <p className="mt-1 text-xs text-muted">{result.events_checked} events checked before the problem.</p>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function LookupCard() {
  const { api, rememberDiagnosis } = useAppData();
  const [value, setValue] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const [found, setFound] = useState<{ diagnosis: Diagnosis; feedback: FeedbackRecord[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  async function lookup(e?: FormEvent) {
    e?.preventDefault();
    const id = value.trim();
    if (!ID_PATTERN.test(id)) {
      setInputError("Enter a diagnosis ID (letters, digits, dots, dashes or underscores).");
      return;
    }
    setInputError(null);
    setLoading(true);
    setError(null);
    setFound(null);
    try {
      const diagnosis = await api.diagnosis(id);
      const feedback = await api.feedback(id);
      rememberDiagnosis(diagnosis);
      setFound({ diagnosis, feedback });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  const top = found ? sortedCauses(found.diagnosis)[0] : undefined;
  return (
    <Card aria-labelledby="lookup-title">
      <CardHeader id="lookup-title" icon={<Search className="h-5 w-5" />} title="Look up a diagnosis"
                  description="Reads one saved diagnosis and its feedback from the audit log." />
      <div className="space-y-4 p-5">
        <form onSubmit={(e) => void lookup(e)} noValidate className="flex flex-wrap items-start gap-2">
          <div className="min-w-[14rem] flex-1">
            <label htmlFor="lookup-id" className="sr-only">Diagnosis ID</label>
            <input id="lookup-id" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Diagnosis ID"
                   aria-invalid={Boolean(inputError)} aria-describedby={inputError ? "lookup-error" : undefined}
                   className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30" />
            {inputError && <p id="lookup-error" className="mt-1.5 text-sm text-danger-text">{inputError}</p>}
          </div>
          <Button type="submit" variant="primary" loading={loading} loadingText="Looking up…">Look up</Button>
        </form>
        {error ? <ErrorAlert error={error} compact /> : null}
        {found && (
          <div className="rounded-lg border border-slate-200 p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono font-semibold">{found.diagnosis.case_id}</span>
              <OutcomeBadge outcome={found.diagnosis.outcome} />{found.diagnosis.escalate && <EscalateBadge />}
            </div>
            <dl className="mt-3 grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted">Recorded</dt><dd>{formatTimestamp(found.diagnosis.created_at)}</dd>
              <dt className="text-muted">Top cause</dt><dd>{top ? humanize(top.cause) : "None claimed"}</dd>
              <dt className="text-muted">Feedback</dt><dd>{found.feedback.length} {found.feedback.length === 1 ? "record" : "records"}</dd>
            </dl>
            {found.feedback.length > 0 && (
              <ul className="mt-3 space-y-1.5 border-t border-slate-100 pt-3">
                {found.feedback.map((f) => (
                  <li key={f.feedback_id} className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge>{f.verdict}</Badge><span>{f.cause_id ?? "Whole diagnosis"}</span>
                    <span className="text-muted">{formatTimestamp(f.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-4 flex flex-wrap gap-3">
              <Link to={`/diagnoses/${encodeURIComponent(found.diagnosis.diagnosis_id)}`} className="rounded font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">Open diagnosis</Link>
              <Link to={`/review?d=${encodeURIComponent(found.diagnosis.diagnosis_id)}`} className="rounded font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">Review it</Link>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

export function AuditPage() {
  const { diagnoses, recentDiagnosisIds } = useAppData();
  return (
    <>
      <PageHeader title="Audit History" description="The backend keeps an append-only, hash-chained SQLite log of every diagnosis and every reviewer verdict." />
      <div className="grid gap-6 lg:grid-cols-2">
        <ChainCard />
        <LookupCard />
        <Card className="lg:col-span-2" aria-labelledby="timeline-title">
          <CardHeader id="timeline-title" icon={<Timer className="h-5 w-5" />} title="Audit timeline" />
          <EmptyState title="Integration pending" icon={<Timer className="h-5 w-5" />}>
            The backend does not have an endpoint that lists audit events yet, so no timeline is shown here
            (nothing is invented). Look up a diagnosis by ID above, or verify the whole chain.
          </EmptyState>
          {recentDiagnosisIds.length > 0 && (
            <div className="border-t border-slate-100 px-5 py-4">
              <h3 className="mb-2 text-sm font-medium">Diagnoses opened in this browser session</h3>
              <ul className="flex flex-wrap gap-2">
                {recentDiagnosisIds.map((id) => {
                  const d = diagnoses.get(id);
                  return d ? (
                    <li key={id}>
                      <Link to={`/diagnoses/${encodeURIComponent(id)}`} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
                        <span className="font-mono">{d.case_id}</span><OutcomeBadge outcome={d.outcome} />
                      </Link>
                    </li>
                  ) : null;
                })}
              </ul>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

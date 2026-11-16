import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { ID_PATTERN } from "../../lib/api";
import { formatTimestamp } from "../../lib/format";
import { useAppData } from "../../state/AppData";
import { OutcomeBadge, EscalateBadge } from "../common/status";
import { Button, Card, CardHeader, EmptyState } from "../common/ui";

/** Choose which saved diagnosis a page should show: by id, or one received in this session. */
export function DiagnosisPicker({ hrefFor, title, children }:
  { hrefFor: (diagnosisId: string) => string; title: string; children?: ReactNode }) {
  const navigate = useNavigate();
  const { diagnoses, recentDiagnosisIds } = useAppData();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const id = value.trim();
    if (!ID_PATTERN.test(id)) {
      setError("Enter a diagnosis ID (letters, digits, dots, dashes or underscores).");
      return;
    }
    setError(null);
    navigate(hrefFor(id));
  }

  return (
    <Card aria-labelledby="picker-title">
      <CardHeader id="picker-title" title={title} description={children} />
      <div className="grid gap-6 p-5 md:grid-cols-2">
        <form onSubmit={submit} noValidate>
          <label htmlFor="picker-id" className="mb-1.5 block text-sm font-medium">Diagnosis ID</label>
          <div className="flex gap-2">
            <input id="picker-id" value={value} onChange={(e) => setValue(e.target.value)} placeholder="e.g. 3f2b…"
                   aria-invalid={Boolean(error)} aria-describedby={error ? "picker-error" : undefined}
                   className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30" />
            <Button type="submit" variant="primary" icon={<Search className="h-4 w-4" aria-hidden />}>Open</Button>
          </div>
          {error && <p id="picker-error" className="mt-1.5 text-sm text-danger-text">{error}</p>}
          <p className="mt-3 text-sm text-muted">
            No diagnosis yet? <Link to="/cases" className="font-medium text-primary hover:underline">Pick a case</Link> and run one.
          </p>
        </form>
        <div>
          <h3 className="mb-2 text-sm font-medium">From this session</h3>
          {recentDiagnosisIds.length === 0 ? (
            <EmptyState title="No diagnoses in this session">Diagnoses you run or open appear here (kept in memory only).</EmptyState>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {recentDiagnosisIds.slice(0, 8).map((id) => {
                const d = diagnoses.get(id);
                if (!d) return null;
                return (
                  <li key={id}>
                    <Link to={hrefFor(id)}
                          className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
                      <span className="font-mono font-medium">{d.case_id}</span>
                      <OutcomeBadge outcome={d.outcome} />
                      {d.escalate && <EscalateBadge />}
                      <span className="ml-auto text-xs text-muted">{formatTimestamp(d.created_at)}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}

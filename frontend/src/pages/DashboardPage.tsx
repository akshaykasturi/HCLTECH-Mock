import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowRight, Database, FolderSearch, RefreshCw, ScrollText, Server, Stethoscope, Workflow } from "lucide-react";
import { deriveHealth } from "../lib/health";
import { formatClock, formatTimestamp, splitRoute } from "../lib/format";
import { useAppData, useCases, useHealth } from "../state/AppData";
import { EscalateBadge, HealthBadge, OutcomeBadge } from "../components/common/status";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorAlert, LoadingBlock, Mono, PageHeader, Skeleton } from "../components/common/ui";

function Kpi({ label, icon, children, footer }: { label: string; icon: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <Card as="div" className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted">{label}</p>
        <span className="rounded-lg bg-primary-soft p-2 text-primary" aria-hidden>{icon}</span>
      </div>
      <div className="mt-3">{children}</div>
      {footer && <p className="mt-2 text-xs text-muted">{footer}</p>}
    </Card>
  );
}

const quickLink = "group flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-medium hover:border-primary/40 hover:bg-primary-soft/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

export function DashboardPage() {
  const cases = useCases();
  const health = useHealth();
  const { diagnoses, recentDiagnosisIds } = useAppData();
  const status = deriveHealth(health.data, health.error);
  const refreshing = cases.loading || health.loading;

  const splitCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const c of cases.data ?? []) counts.set(c.split, (counts.get(c.split) ?? 0) + 1);
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [cases.data]);
  const preview = useMemo(() => [...(cases.data ?? [])].sort((a, b) => a.id.localeCompare(b.id)).slice(0, 6), [cases.data]);

  return (
    <>
      <PageHeader title="Dashboard"
                  description="Overview of the case data and backend status. Every number here comes from the FastAPI backend."
                  actions={<Button onClick={() => { void cases.reload(); void health.reload(); }} loading={refreshing}
                                   loadingText="Refreshing…" icon={<RefreshCw className="h-4 w-4" aria-hidden />}>Refresh</Button>} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Total cases" icon={<FolderSearch className="h-4 w-4" />}
             footer={cases.loadedAt ? `Loaded at ${formatClock(cases.loadedAt)}` : undefined}>
          {cases.loading && !cases.data ? <Skeleton className="h-8 w-16" /> :
           cases.data ? <p className="text-3xl font-semibold tabular-nums" data-testid="total-cases">{cases.data.length}</p> :
           <p className="text-sm text-muted">Unavailable</p>}
        </Kpi>
        <Kpi label="API" icon={<Server className="h-4 w-4" />}>
          {health.loading && !health.data && !health.error ? <Skeleton className="h-6 w-24" /> : <HealthBadge state={status.api} />}
        </Kpi>
        <Kpi label="Audit database" icon={<Database className="h-4 w-4" />}>
          {health.loading && !health.data && !health.error ? <Skeleton className="h-6 w-24" /> : <HealthBadge state={status.database} />}
        </Kpi>
        <Kpi label="Diagnosis pipeline" icon={<Workflow className="h-4 w-4" />}
             footer={health.data?.pipeline_detail && health.data.pipeline !== "ready" ? health.data.pipeline_detail : undefined}>
          {health.loading && !health.data && !health.error ? <Skeleton className="h-6 w-24" /> :
           <HealthBadge state={status.pipeline} label={status.pipeline === "healthy" ? "Ready" : undefined} />}
        </Kpi>
      </div>

      {(cases.error || health.error) && (
        <div className="mt-4 space-y-3">
          {cases.error ? <ErrorAlert error={cases.error} onRetry={() => void cases.reload()} retrying={cases.loading} /> : null}
          {health.error ? <ErrorAlert error={health.error} onRetry={() => void health.reload()} retrying={health.loading} /> : null}
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" aria-labelledby="preview-title">
          <CardHeader id="preview-title" title="Cases" description="The first cases by ID. Open the Case Explorer to search all of them."
                      actions={<Link to="/cases" className="inline-flex items-center gap-1 rounded text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
                        View all <ArrowRight className="h-4 w-4" aria-hidden /></Link>} />
          {cases.loading && !cases.data ? <LoadingBlock label="Loading cases" rows={5} /> :
           !cases.data ? <EmptyState title="Cases could not be loaded">Use Retry above once the backend is reachable.</EmptyState> :
           cases.data.length === 0 ? <EmptyState title="No cases">The backend returned an empty case list.</EmptyState> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[32rem] text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
                  <tr><th scope="col" className="px-5 py-2 font-medium">Case</th><th scope="col" className="px-3 py-2 font-medium">Route</th>
                      <th scope="col" className="px-3 py-2 font-medium">Summary</th><th scope="col" className="px-5 py-2"><span className="sr-only">Action</span></th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preview.map((c) => {
                    const { method, path } = splitRoute(c.route);
                    return (
                      <tr key={c.id} className="hover:bg-slate-50">
                        <td className="px-5 py-2.5 font-mono font-medium">{c.id}</td>
                        <td className="px-3 py-2.5"><Mono><span className="font-semibold">{method}</span> {path}</Mono></td>
                        <td className="px-3 py-2.5 text-slate-700">{c.summary}</td>
                        <td className="px-5 py-2.5 text-right">
                          <Link to={`/diagnosis/${encodeURIComponent(c.id)}`} className="rounded text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                                aria-label={`Diagnose ${c.id}`}>Diagnose</Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card aria-labelledby="quick-title">
            <CardHeader id="quick-title" title="Quick actions" />
            <div className="grid gap-2 p-4">
              <Link to="/cases" className={quickLink}><span className="flex items-center gap-2"><FolderSearch className="h-4 w-4 text-primary" aria-hidden />Browse cases</span><ArrowRight className="h-4 w-4 text-muted group-hover:text-primary" aria-hidden /></Link>
              <Link to="/diagnosis" className={quickLink}><span className="flex items-center gap-2"><Stethoscope className="h-4 w-4 text-primary" aria-hidden />Diagnosis workspace</span><ArrowRight className="h-4 w-4 text-muted group-hover:text-primary" aria-hidden /></Link>
              <Link to="/audit" className={quickLink}><span className="flex items-center gap-2"><ScrollText className="h-4 w-4 text-primary" aria-hidden />Verify audit chain</span><ArrowRight className="h-4 w-4 text-muted group-hover:text-primary" aria-hidden /></Link>
              <Link to="/system-health" className={quickLink}><span className="flex items-center gap-2"><Activity className="h-4 w-4 text-primary" aria-hidden />System health</span><ArrowRight className="h-4 w-4 text-muted group-hover:text-primary" aria-hidden /></Link>
            </div>
          </Card>

          <Card aria-labelledby="split-title">
            <CardHeader id="split-title" title="Cases by split" description="Counted from GET /api/cases." />
            {splitCounts.length === 0 ? <p className="px-5 py-4 text-sm text-muted">No data yet.</p> : (
              <ul className="divide-y divide-slate-100">
                {splitCounts.map(([split, n]) => (
                  <li key={split} className="flex items-center justify-between px-5 py-2.5 text-sm">
                    <Badge>{split}</Badge><span className="font-mono tabular-nums">{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card aria-labelledby="session-title">
            <CardHeader id="session-title" title="Diagnoses in this session" description="Kept in this browser tab's memory only." />
            {recentDiagnosisIds.length === 0 ? (
              <EmptyState title="No diagnoses yet">Run a diagnosis from the Case Explorer.</EmptyState>
            ) : (
              <ul className="divide-y divide-slate-100">
                {recentDiagnosisIds.slice(0, 5).map((id) => {
                  const d = diagnoses.get(id);
                  return d ? (
                    <li key={id}>
                      <Link to={`/diagnoses/${encodeURIComponent(id)}`} className="flex flex-wrap items-center gap-2 px-5 py-2.5 text-sm hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
                        <span className="font-mono font-medium">{d.case_id}</span><OutcomeBadge outcome={d.outcome} />{d.escalate && <EscalateBadge />}
                        <span className="ml-auto text-xs text-muted">{formatTimestamp(d.created_at)}</span>
                      </Link>
                    </li>
                  ) : null;
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, RefreshCw, Search, Stethoscope, X } from "lucide-react";
import { splitRoute } from "../lib/format";
import type { CaseSummary } from "../lib/types";
import { useDebounced } from "../hooks/useDebounced";
import { useCases } from "../state/AppData";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorAlert, LoadingBlock, Mono, PageHeader } from "../components/common/ui";

export const PAGE_SIZE = 15;
type SortKey = "id" | "route" | "split";

const selectClass = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30";

function SortHeader({ label, column, sort, onSort }:
  { label: string; column: SortKey; sort: { key: SortKey; dir: "asc" | "desc" }; onSort: (k: SortKey) => void }) {
  const active = sort.key === column;
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th scope="col" aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"} className="px-3 py-2 font-medium first:pl-5">
      <button type="button" onClick={() => onSort(column)}
              className="inline-flex items-center gap-1 rounded uppercase tracking-wide hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
        {label}<Icon className="h-3.5 w-3.5" aria-hidden />
      </button>
    </th>
  );
}

export function CasesPage() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useCases();
  const [query, setQuery] = useState("");
  const [route, setRoute] = useState("");
  const [split, setSplit] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "id", dir: "asc" });
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const debouncedQuery = useDebounced(query, 200);

  const routes = useMemo(() => [...new Set((data ?? []).map((c) => c.route))].sort(), [data]);
  const splits = useMemo(() => [...new Set((data ?? []).map((c) => c.split))].sort(), [data]);

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase();
    const rows = (data ?? []).filter((c) =>
      (!route || c.route === route) && (!split || c.split === split)
      && (!q || c.id.toLowerCase().includes(q) || c.route.toLowerCase().includes(q) || c.summary.toLowerCase().includes(q)));
    const dir = sort.dir === "asc" ? 1 : -1;
    return rows.sort((a, b) => (a[sort.key].localeCompare(b[sort.key]) || a.id.localeCompare(b.id)) * dir);
  }, [data, debouncedQuery, route, split, sort]);

  useEffect(() => setPage(1), [debouncedQuery, route, split, sort]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pageCount);
  const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const selected: CaseSummary | undefined = (data ?? []).find((c) => c.id === selectedId);
  const filtersActive = Boolean(query || route || split);

  const onSort = (key: SortKey) => setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));
  const clear = () => { setQuery(""); setRoute(""); setSplit(""); };

  return (
    <>
      <PageHeader title="Case Explorer" description="Every failure case the backend serves. Evaluation labels are never sent to the browser."
                  actions={<Button onClick={() => void reload()} loading={loading} loadingText="Refreshing…"
                                   icon={<RefreshCw className="h-4 w-4" aria-hidden />}>Refresh</Button>} />

      <Card className="mb-4 p-4" as="div">
        <div className="grid gap-3 md:grid-cols-[1fr,auto,auto,auto]">
          <div className="relative">
            <label htmlFor="case-search" className="sr-only">Search cases by ID, route or summary</label>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input id="case-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                   placeholder="Search by case ID, route or summary"
                   className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <div>
            <label htmlFor="route-filter" className="sr-only">Filter by route</label>
            <select id="route-filter" value={route} onChange={(e) => setRoute(e.target.value)} className={`${selectClass} w-full md:w-56`}>
              <option value="">All routes</option>
              {routes.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="split-filter" className="sr-only">Filter by split</label>
            <select id="split-filter" value={split} onChange={(e) => setSplit(e.target.value)} className={`${selectClass} w-full md:w-40`}>
              <option value="">All splits</option>
              {splits.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <Button variant="ghost" onClick={clear} disabled={!filtersActive} icon={<X className="h-4 w-4" aria-hidden />}>Clear</Button>
        </div>
      </Card>

      {error ? <div className="mb-4"><ErrorAlert error={error} onRetry={() => void reload()} retrying={loading} /></div> : null}

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" aria-labelledby="cases-title">
          <CardHeader id="cases-title" title="Cases"
                      description={data ? <span aria-live="polite">{filtered.length} of {data.length} cases</span> : undefined} />
          {loading && !data ? <LoadingBlock label="Loading cases" rows={8} /> :
           !data ? <EmptyState title="Cases could not be loaded">Use Retry once the backend is reachable.</EmptyState> :
           data.length === 0 ? <EmptyState title="No cases">The backend returned an empty case list.</EmptyState> :
           filtered.length === 0 ? (
             <EmptyState title="No cases match your filters" icon={<Search className="h-5 w-5" />}
                         action={<Button onClick={clear}>Clear filters</Button>}>Try a different search or route.</EmptyState>
           ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] text-left text-sm">
                  <caption className="sr-only">Cases, sortable by ID, route and split. Select a row to preview it.</caption>
                  <thead className="bg-slate-50 text-xs text-muted">
                    <tr>
                      <SortHeader label="Case" column="id" sort={sort} onSort={onSort} />
                      <SortHeader label="Route" column="route" sort={sort} onSort={onSort} />
                      <th scope="col" className="px-3 py-2 font-medium uppercase tracking-wide">Summary</th>
                      <SortHeader label="Split" column="split" sort={sort} onSort={onSort} />
                      <th scope="col" className="px-5 py-2"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rows.map((c) => {
                      const { method, path } = splitRoute(c.route);
                      const isSelected = c.id === selectedId;
                      return (
                        <tr key={c.id} aria-selected={isSelected} onClick={() => setSelectedId(c.id)}
                            className={`cursor-pointer ${isSelected ? "bg-primary-soft/60" : "hover:bg-slate-50"}`}>
                          <td className="py-2.5 pl-5 pr-3">
                            <button type="button" onClick={(e) => { e.stopPropagation(); setSelectedId(c.id); }}
                                    className="rounded font-mono font-medium text-ink hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                                    aria-label={`Preview ${c.id}`} aria-pressed={isSelected}>{c.id}</button>
                          </td>
                          <td className="px-3 py-2.5"><Mono><span className="font-semibold">{method}</span> {path}</Mono></td>
                          <td className="px-3 py-2.5 text-slate-700">{c.summary}</td>
                          <td className="px-3 py-2.5"><Badge>{c.split}</Badge></td>
                          <td className="px-5 py-2.5 text-right">
                            <Link to={`/diagnosis/${encodeURIComponent(c.id)}`} onClick={(e) => e.stopPropagation()}
                                  className="rounded text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                                  aria-label={`Diagnose ${c.id}`}>Diagnose</Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <nav aria-label="Pagination" className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3 text-sm">
                <p className="text-muted">Page {current} of {pageCount}</p>
                <div className="flex gap-2">
                  <Button onClick={() => setPage(current - 1)} disabled={current <= 1} icon={<ChevronLeft className="h-4 w-4" aria-hidden />}>Previous</Button>
                  <Button onClick={() => setPage(current + 1)} disabled={current >= pageCount}>Next<ChevronRight className="h-4 w-4" aria-hidden /></Button>
                </div>
              </nav>
            </>
          )}
        </Card>

        <Card aria-labelledby="case-preview-title" className="h-fit xl:sticky xl:top-20">
          <CardHeader id="case-preview-title" title="Case preview" />
          {!selected ? (
            <EmptyState title="No case selected">Select a case in the table to preview it here.</EmptyState>
          ) : (
            <div className="space-y-4 p-5 text-sm">
              <p className="font-mono text-lg font-semibold">{selected.id}</p>
              <dl className="space-y-3">
                <div><dt className="text-xs uppercase tracking-wide text-muted">Route</dt><dd><Mono>{selected.route}</Mono></dd></div>
                <div><dt className="text-xs uppercase tracking-wide text-muted">Summary</dt><dd className="text-slate-700">{selected.summary}</dd></div>
                <div><dt className="text-xs uppercase tracking-wide text-muted">Split</dt><dd><Badge>{selected.split}</Badge></dd></div>
              </dl>
              <Button variant="primary" className="w-full" icon={<Stethoscope className="h-4 w-4" aria-hidden />}
                      onClick={() => navigate(`/diagnosis/${encodeURIComponent(selected.id)}`)}>
                Open diagnosis workspace
              </Button>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

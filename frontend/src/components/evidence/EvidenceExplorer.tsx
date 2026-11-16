import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, Search } from "lucide-react";
import { causeEvidenceIds, evidenceAnchor, evidenceIndex, kindLabel, resolveIds, sortedCauses, unresolvedIds } from "../../lib/evidence";
import { humanize, valueToText } from "../../lib/format";
import type { Diagnosis, EvidenceItem } from "../../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState } from "../common/ui";
import { KindBadge } from "./EvidenceBits";

type CitedBy = { cause: string; role: "supports" | "contradicts" }[];

function EvidenceCard({ item, focused, citedBy, defaultOpen }:
  { item: EvidenceItem; focused: boolean; citedBy: CitedBy; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => { if (defaultOpen) setOpen(true); }, [defaultOpen]);
  const entries = Object.entries(item.data ?? {});
  const panelId = `${evidenceAnchor(item.id)}-details`;
  return (
    <li id={evidenceAnchor(item.id)} tabIndex={-1} aria-label={`Evidence ${item.id}`}
        className={`scroll-mt-24 rounded-lg border p-4 transition-shadow focus:outline-none ${
          focused ? "border-primary ring-2 ring-primary/30" : item.kind === "missing" ? "border-dashed border-danger/40 bg-danger-soft/30" : "border-slate-200"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <KindBadge kind={item.kind} />
        <code className="break-all font-mono text-xs text-slate-600">{item.id}</code>
        {focused && <Badge tone="primary">Cited</Badge>}
      </div>
      <p className="mt-2 text-sm text-ink">{item.text}</p>
      {citedBy.length > 0 && (
        <p className="mt-2 flex flex-wrap gap-1.5 text-xs text-muted">
          <span>Used by:</span>
          {citedBy.map((c) => (
            <Badge key={`${c.cause}-${c.role}`} tone={c.role === "supports" ? "success" : "danger"}>
              {c.role === "supports" ? "supports" : "contradicts"} {c.cause}
            </Badge>
          ))}
        </p>
      )}
      {entries.length > 0 && (
        <>
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls={panelId}
                  className="mt-3 inline-flex items-center gap-1 rounded text-sm font-medium text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
            {open ? <ChevronUp className="h-4 w-4" aria-hidden /> : <ChevronDown className="h-4 w-4" aria-hidden />}
            {open ? "Hide details" : `Show details (${entries.length} fields)`}
          </button>
          {open && (
            <dl id={panelId} className="mt-3 grid gap-x-4 gap-y-2 rounded-lg bg-slate-50 p-3 text-xs sm:grid-cols-[minmax(8rem,auto),1fr]">
              {entries.map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="font-mono text-muted">{key}</dt>
                  <dd className="min-w-0"><pre className="whitespace-pre-wrap break-all font-mono text-slate-800">{valueToText(value)}</pre></dd>
                </div>
              ))}
            </dl>
          )}
        </>
      )}
    </li>
  );
}

export function EvidenceExplorer({ diagnosis, focusId }: { diagnosis: Diagnosis; focusId: string | null }) {
  const [kinds, setKinds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [cause, setCause] = useState("");
  const index = useMemo(() => evidenceIndex(diagnosis), [diagnosis]);
  const causes = useMemo(() => sortedCauses(diagnosis), [diagnosis]);
  const unresolved = useMemo(() => unresolvedIds(diagnosis), [diagnosis]);
  const focusMissing = focusId !== null && !index.has(focusId);

  const kindCounts = useMemo(() => {
    const m = new Map<string, number>();
    diagnosis.evidence.forEach((e) => m.set(e.kind, (m.get(e.kind) ?? 0) + 1));
    return [...m.entries()];
  }, [diagnosis]);

  const citedBy = useMemo(() => {
    const m = new Map<string, CitedBy>();
    for (const c of causes) {
      const { supporting, contradicting } = causeEvidenceIds(c);
      supporting.forEach((id) => m.set(id, [...(m.get(id) ?? []), { cause: c.cause, role: "supports" }]));
      contradicting.forEach((id) => m.set(id, [...(m.get(id) ?? []), { cause: c.cause, role: "contradicts" }]));
    }
    return m;
  }, [causes]);

  // Jump to a cited item: clear filters that would hide it, then scroll to it and move focus there.
  useEffect(() => {
    if (!focusId || !index.has(focusId)) return;
    setKinds(new Set());
    setQuery("");
    setCause("");
    const timer = window.setTimeout(() => {
      const el = document.getElementById(evidenceAnchor(focusId));
      el?.scrollIntoView?.({ block: "center" });
      el?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [focusId, index]);

  const matches = (e: EvidenceItem) => {
    const q = query.trim().toLowerCase();
    return (kinds.size === 0 || kinds.has(e.kind))
      && (!q || e.id.toLowerCase().includes(q) || e.text.toLowerCase().includes(q) || e.kind.toLowerCase().includes(q));
  };
  const toggleKind = (k: string) => setKinds((prev) => {
    const next = new Set(prev);
    if (next.has(k)) next.delete(k); else next.add(k);
    return next;
  });

  const renderList = (items: EvidenceItem[]) => (
    <ul className="space-y-3">
      {items.map((item) => (
        <EvidenceCard key={item.id} item={item} focused={item.id === focusId} citedBy={citedBy.get(item.id) ?? []}
                      defaultOpen={item.id === focusId} />
      ))}
    </ul>
  );

  const selectedCause = causes.find((c) => c.cause === cause);
  const filtered = diagnosis.evidence.filter(matches);

  return (
    <div className="space-y-4">
      {(unresolved.length > 0 || focusMissing) && (
        <div role="note" className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-text" aria-hidden />
          <div>
            {focusMissing && <p>Evidence <span className="font-mono">{focusId}</span> is not in this diagnosis.</p>}
            {unresolved.length > 0 && <p>Cited but missing from the evidence list: <span className="font-mono">{unresolved.join(", ")}</span></p>}
          </div>
        </div>
      )}

      <Card as="div" className="p-4">
        <div className="grid gap-3 lg:grid-cols-[1fr,16rem]">
          <div className="relative">
            <label htmlFor="evidence-search" className="sr-only">Search evidence</label>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input id="evidence-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search evidence text or ID"
                   className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <div>
            <label htmlFor="evidence-cause" className="sr-only">Group evidence by cause</label>
            <select id="evidence-cause" value={cause} onChange={(e) => setCause(e.target.value)} disabled={causes.length === 0}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:bg-slate-50">
              <option value="">{causes.length === 0 ? "No ranked causes" : "All evidence"}</option>
              {causes.map((c) => <option key={c.cause} value={c.cause}>Evidence for #{c.rank} {humanize(c.cause)}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter by evidence kind">
          {kindCounts.map(([k, n]) => (
            <button key={k} type="button" aria-pressed={kinds.has(k)} onClick={() => toggleKind(k)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${
                      kinds.has(k) ? "border-primary bg-primary text-white" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}>
              {kindLabel(k)} · {n}
            </button>
          ))}
          {kinds.size > 0 && <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => setKinds(new Set())}>Show all kinds</Button>}
        </div>
      </Card>

      {diagnosis.evidence.length === 0 ? (
        <Card as="div"><EmptyState title="No evidence">The backend returned no evidence items for this diagnosis.</EmptyState></Card>
      ) : selectedCause ? (
        (() => {
          const ids = causeEvidenceIds(selectedCause);
          const group = (title: string, refs: ReturnType<typeof resolveIds>, empty: string) => {
            const found = refs.filter((r) => r.item && matches(r.item)).map((r) => r.item as EvidenceItem);
            const missing = refs.filter((r) => !r.item);
            const headingId = `group-${title.toLowerCase().replace(/\s+/g, "-")}`;
            return (
              <Card aria-labelledby={headingId}>
                <CardHeader id={headingId} title={title} description={`${refs.length} referenced`} />
                <div className="space-y-3 p-4">
                  {missing.map((r) => (
                    <p key={r.id} className="flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning-text">
                      <AlertTriangle className="h-4 w-4" aria-hidden />Referenced evidence <span className="font-mono">{r.id}</span> is not in this diagnosis.
                    </p>
                  ))}
                  {found.length > 0 ? renderList(found) : missing.length === 0 && <p className="text-sm text-muted">{empty}</p>}
                </div>
              </Card>
            );
          };
          const missingItems = diagnosis.evidence.filter((e) => e.kind === "missing" && matches(e));
          return (
            <div className="space-y-4">
              {group("Supporting evidence", resolveIds(ids.supporting, index), "No supporting evidence for this cause.")}
              {group("Contradicting evidence", resolveIds(ids.contradicting, index), "No contradicting evidence for this cause.")}
              <Card aria-labelledby="group-missing">
                <CardHeader id="group-missing" title="Missing evidence" description="Data the pipeline expected but could not find." />
                <div className="p-4">{missingItems.length > 0 ? renderList(missingItems) : <p className="text-sm text-muted">Nothing missing.</p>}</div>
              </Card>
            </div>
          );
        })()
      ) : filtered.length === 0 ? (
        <Card as="div"><EmptyState title="No evidence matches" action={<Button onClick={() => { setKinds(new Set()); setQuery(""); }}>Clear filters</Button>} /></Card>
      ) : (
        <Card aria-labelledby="all-evidence">
          <CardHeader id="all-evidence" title="Evidence" description={`${filtered.length} of ${diagnosis.evidence.length} items`} />
          <div className="p-4">{renderList(filtered)}</div>
        </Card>
      )}
    </div>
  );
}

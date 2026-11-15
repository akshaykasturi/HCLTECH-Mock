// Audit log: every saved analysis, a summary of outcomes and feedback, and the full record on click.
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { generatorText, OUTCOME, pct, when } from "../lib/words";
import Result from "./Result";

const DOT = { RECOMMEND: "bg-go", CLARIFY: "bg-hold", ESCALATE: "bg-stop" };

// The backend answers 503 DATABASE_UNAVAILABLE when the audit database can't be reached.
function errorText(e) {
  return e.code === "DATABASE_UNAVAILABLE"
    ? "The audit log database can't be reached right now. Analyses still work but aren't being saved."
    : e.message;
}

// A stored record is flat; the result view expects the shape /api/analyze returns.
function toResult(r) {
  return {
    ...r,
    analysis_id: r.analysis_id || r.id,
    classification: { category: r.category, subcategory: r.subcategory, priority: r.priority,
      confidence: r.classifier_confidence },
    reasons: r.reasons || [],
  };
}

function Summary({ stats }) {
  if (!stats) return null;
  const total = stats.total_analyses || 0;
  const order = ["RECOMMEND", "CLARIFY", "ESCALATE"];
  const verdicts = Object.entries(stats.by_verdict || {});
  return (
    <section className="grid gap-6 border-b border-rule pb-6 md:grid-cols-[1.4fr_1fr_1fr]">
      <div>
        <p className="display text-[34px] font-bold leading-none">{total}</p>
        <p className="text-[14px] text-steel">tickets analysed</p>
        <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-rule" role="img"
          aria-label={order.map((o) => `${stats.by_outcome?.[o] || 0} ${OUTCOME[o].label}`).join(", ")}>
          {order.map((o) => (
            <span key={o} className={DOT[o]} style={{ width: total ? `${((stats.by_outcome?.[o] || 0) / total) * 100}%` : 0 }} />
          ))}
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-4 text-[13px] text-steel">
          {order.map((o) => (
            <li key={o} className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${DOT[o]}`} />{stats.by_outcome?.[o] || 0} {OUTCOME[o].label.toLowerCase()}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="text-[14px] font-semibold">Analyst feedback</p>
        {verdicts.length ? (
          <ul className="mt-1 text-[14px] text-steel">
            {verdicts.map(([v, n]) => <li key={v}>{n} {v === "unresolved" ? "didn't resolve it" : v}</li>)}
          </ul>
        ) : <p className="mt-1 text-[14px] text-steel">None yet</p>}
      </div>
      <div>
        <p className="text-[14px] font-semibold">Who wrote the steps</p>
        <ul className="mt-1 text-[14px] text-steel">
          {Object.entries(stats.generator_share || {}).map(([g, share]) => (
            <li key={g}>{pct(share)} {g === "none" ? "stopped before writing" : generatorText(g)}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function History() {
  const [filter, setFilter] = useState("");
  const [rows, setRows] = useState(null);
  const [stats, setStats] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setError("");
    Promise.all([api.listAnalyses(filter), api.stats()])
      .then(([list, s]) => { if (live) { setRows(list); setStats(s); } })
      .catch((e) => live && setError(errorText(e)));
    return () => { live = false; };
  }, [filter]);

  async function open(id) {
    try { setSelected(toResult(await api.getAnalysis(id))); } catch (e) { setError(errorText(e)); }
  }

  if (selected) {
    return (
      <div>
        <button type="button" className="btn-quiet mb-6" onClick={() => setSelected(null)}>Back to all analyses</button>
        <p className="mb-1 text-[14px] text-steel">{when(selected.created_at)}</p>
        <h2 className="display mb-1 text-[26px] font-bold">{selected.title}</h2>
        <p className="mb-6 max-w-[70ch] font-serif text-[16px] leading-relaxed text-ink">{selected.description}</p>
        <Result result={selected} />
        {selected.feedback?.length > 0 && (
          <section className="mt-6 border-t border-rule pt-5">
            <h3 className="display text-[22px] font-semibold">Feedback on this analysis</h3>
            <ul className="mt-2 space-y-1 text-[15px]">
              {selected.feedback.map((f) => (
                <li key={f.id}><span className="font-semibold">{f.verdict}</span> on {f.target}{f.comment ? `: ${f.comment}` : ""}
                  <span className="text-steel">, {when(f.created_at)}</span></li>
              ))}
            </ul>
          </section>
        )}
      </div>
    );
  }

  return (
    <div>
      <Summary stats={stats} />
      <div className="mt-6 flex flex-wrap items-center gap-2" role="group" aria-label="Filter by outcome">
        {["", "RECOMMEND", "CLARIFY", "ESCALATE"].map((o) => (
          <button key={o || "all"} type="button" onClick={() => setFilter(o)} aria-pressed={filter === o}
            className={`rounded-full border px-3 py-1 text-[14px] ${filter === o ? "border-ink bg-ink text-sheet" : "border-rule hover:border-steel"}`}>
            {o ? OUTCOME[o].label : "All"}
          </button>
        ))}
      </div>
      {error && <p className="mt-4 text-[14px] text-stop" role="alert">{error}</p>}
      {rows && rows.length === 0 && (
        <p className="mt-8 text-[15px] text-steel">No analyses yet. Analyse a ticket and it will appear here.</p>
      )}
      {rows && rows.length > 0 && (
        <table className="mt-4 w-full text-left text-[15px]">
          <thead className="text-[13px] text-steel">
            <tr className="border-b border-rule">
              <th className="py-2 font-normal">When</th><th className="py-2 font-normal">Ticket</th>
              <th className="hidden py-2 font-normal md:table-cell">Category</th>
              <th className="py-2 font-normal">Outcome</th><th className="hidden py-2 text-right font-normal sm:table-cell">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.analysis_id} className="cursor-pointer border-b border-rule hover:bg-sheet" onClick={() => open(r.analysis_id)}>
                <td className="whitespace-nowrap py-2.5 pr-3 text-steel">{when(r.created_at)}</td>
                <td className="py-2.5 pr-3">
                  <button type="button" className="text-left hover:underline" onClick={(e) => { e.stopPropagation(); open(r.analysis_id); }}>
                    {r.title}
                  </button>
                </td>
                <td className="hidden py-2.5 pr-3 text-steel md:table-cell">{r.category}</td>
                <td className="py-2.5 pr-3">
                  <span className="inline-flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${DOT[r.outcome]}`} />{OUTCOME[r.outcome].label}</span>
                </td>
                <td className="hidden py-2.5 text-right sm:table-cell">{pct(r.confidence)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

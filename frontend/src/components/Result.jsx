// The analysis result: outcome, the route of checks, the steps with their quotes, and the matched records.
import { useState } from "react";
import { OUTCOME, pct, reasonText } from "../lib/words";
import Feedback from "./Feedback";
import RouteTrack from "./RouteTrack";

const ASK = [
  "Which application or device is affected?",
  "What exactly happens, and is there an error message or code?",
  "When did it start, and does it affect anyone else?",
];

const TEXT = { go: "text-go", hold: "text-hold", stop: "text-stop" };
const BAR = { go: "bg-go", hold: "bg-hold", stop: "bg-stop" };

function Outcome({ result }) {
  const o = OUTCOME[result.outcome];
  const reasons = result.reasons.filter((r) => !r.startsWith("LLM_FAILED") || result.outcome !== "RECOMMEND");
  return (
    <header className="relative border-b border-rule pb-5 pl-5">
      <span className={`absolute left-0 top-1 h-[calc(100%-1.5rem)] w-[5px] rounded-[1px] ${BAR[o.color]}`} aria-hidden="true" />
      <h2 className={`display text-[40px] font-bold leading-none ${TEXT[o.color]}`}>{o.label}</h2>
      <p className="mt-2 max-w-[60ch] text-[15px] text-ink">{o.hint}</p>
      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[14px]">
        <div><dt className="inline text-steel">Overall confidence </dt><dd className="inline font-semibold">{pct(result.confidence)}</dd></div>
        <div><dt className="inline text-steel">{result.outcome === "RECOMMEND" ? "Category " : "Best guess "}</dt><dd className="inline">{result.classification.category} / {result.classification.subcategory}</dd></div>
        <div><dt className="inline text-steel">Priority </dt><dd className="inline font-semibold">{result.classification.priority}</dd></div>
      </dl>
      {reasons.length > 0 && (
        <ul className="mt-3 space-y-0.5 text-[14px] text-steel">
          {reasons.map((r) => <li key={r}>{reasonText(r)}</li>)}
        </ul>
      )}
    </header>
  );
}

function Steps({ result, saved }) {
  const rec = result.recommendation;
  if (!rec && result.reasons.includes("TOO_VAGUE")) {
    return (
      <section className="py-5">
        <h3 className="display text-[22px] font-semibold">Ask the requester</h3>
        <ul className="mt-3 max-w-[60ch] list-disc space-y-1 pl-5 text-[16px] leading-relaxed">
          {ASK.map((q) => <li key={q}>{q}</li>)}
        </ul>
        <div className="mt-4"><Feedback analysisId={result.analysis_id} target="recommendation" disabled={!saved} /></div>
      </section>
    );
  }
  if (!rec) {
    return (
      <section className="py-5">
        <h3 className="display text-[22px] font-semibold">No steps drafted</h3>
        <p className="mt-1 max-w-[60ch] text-[15px] text-steel">
          The safety and evidence check stopped this ticket before any AI was asked, so nothing here can be invented.
          The similar records below are shown for context only.
        </p>
        <div className="mt-3"><Feedback analysisId={result.analysis_id} target="recommendation" disabled={!saved} /></div>
      </section>
    );
  }
  return (
    <section className="py-5">
      <h3 className="display text-[22px] font-semibold">Steps to try</h3>
      <ol className="mt-3 space-y-2">
        {rec.steps.map((s, i) => (
          <li key={i} className="grid grid-cols-[22px_1fr] text-[16px] leading-relaxed">
            <span className="font-semibold text-route">{i + 1}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
      {rec.citations.length > 0 && (
        <div className="mt-5">
          <h4 className="text-[14px] font-semibold text-steel">Where the steps come from</h4>
          <ul className="mt-2 space-y-3">
            {rec.citations.map((c, i) => (
              <li key={i} className="border-l-2 border-route/40 pl-3">
                <blockquote className="font-serif text-[16px] italic leading-relaxed text-ink">{c.excerpt}</blockquote>
                <p className="mt-1 text-[13px] text-steel"><span className="font-semibold text-ink">{c.source_id}</span>, {c.reason}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-5"><Feedback analysisId={result.analysis_id} target="recommendation" disabled={!saved} /></div>
    </section>
  );
}

function Matches({ result, saved }) {
  const [open, setOpen] = useState(null);
  if (!result.matches?.length || result.reasons.includes("TOO_VAGUE")) return null;
  return (
    <section className="border-t border-rule py-5">
      <h3 className="display text-[22px] font-semibold">Similar records</h3>
      <p className="mt-1 text-[14px] text-steel">Past resolved tickets and approved guides, most similar first.</p>
      <ul className="mt-3 divide-y divide-rule">
        {result.matches.map((m) => (
          <li key={m.source_id} className="py-3">
            <button type="button" onClick={() => setOpen(open === m.source_id ? null : m.source_id)}
              aria-expanded={open === m.source_id}
              className="grid w-full grid-cols-[92px_1fr_auto] items-baseline gap-3 text-left">
              <span className="text-[14px] font-semibold text-route">{m.source_id}</span>
              <span className="text-[15px]">{m.title}</span>
              <span className="text-[13px] text-steel">{m.source_type === "kb" ? "Guide" : "Past ticket"}</span>
            </button>
            {open === m.source_id && (
              <div className="ml-[104px] mt-2">
                <p className="text-[13px] text-steel">
                  {[m.metadata?.category, m.metadata?.application, m.metadata?.created_at?.slice(0, 10)].filter(Boolean).join(", ")}
                </p>
                <p className="mt-1 max-w-[65ch] text-[15px] leading-relaxed">{m.text}</p>
                <div className="mt-2"><Feedback compact analysisId={result.analysis_id} target={`match:${m.source_id}`} disabled={!saved} /></div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function Result({ result }) {
  const saved = !result.reasons.includes("AUDIT_WRITE_FAILED");
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0">
        <Outcome result={result} />
        <Steps result={result} saved={saved} />
        <Matches result={result} saved={saved} />
      </div>
      <aside className="lg:border-l lg:border-rule lg:pl-8">
        <h3 className="display mb-4 text-[22px] font-semibold">How this was decided</h3>
        <RouteTrack key={result.analysis_id} result={result} />
      </aside>
    </div>
  );
}

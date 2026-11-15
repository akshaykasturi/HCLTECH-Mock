// Page shell: header with backend status, two views (analyse, history).
import { useEffect, useState } from "react";
import { api } from "./lib/api";
import { generatorText } from "./lib/words";
import History from "./components/History";
import Result from "./components/Result";
import RouteTrack from "./components/RouteTrack";
import TicketForm from "./components/TicketForm";

function Status() {
  const [health, setHealth] = useState(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    api.health().then(setHealth).catch(() => setDown(true));
  }, []);
  if (down) return <span className="flex items-center gap-2 text-[13px] text-stop"><span className="h-2 w-2 rounded-full bg-stop" />Backend unreachable</span>;
  if (!health) return <span className="text-[13px] text-steel">Connecting…</span>;
  const chain = (health.llm_chain || []).map((p) => generatorText(p).split(" (")[0]).join(", then ");
  return (
    <span className="flex items-center gap-2 text-[13px] text-steel" title={`${health.documents_indexed} records indexed`}>
      <span className="h-2 w-2 rounded-full bg-go" />
      {health.documents_indexed} records indexed. Writer: {chain}
    </span>
  );
}

function Empty() {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="max-w-[52ch] pt-2">
        <h2 className="display text-[40px] font-bold leading-[1.02]">Every answer shows its evidence.</h2>
        <p className="mt-4 text-[16px] leading-relaxed text-steel">
          Paste a ticket or load an example. The assistant finds similar past cases, drafts steps only when the evidence
          is strong, and quotes the source for each one. When the evidence is weak or the ticket looks unsafe, it says so
          and hands over to a person.
        </p>
      </div>
      <aside className="lg:border-l lg:border-rule lg:pl-8">
        <h3 className="display mb-4 text-[22px] font-semibold">The checks each ticket passes</h3>
        <RouteTrack result={null} />
      </aside>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState("analyse");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function analyse(ticket) {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.analyze(ticket));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const tab = (id, label) => (
    <button type="button" onClick={() => setView(id)} aria-current={view === id ? "page" : undefined}
      className={`border-b-2 px-1 pb-2 text-[15px] ${view === id ? "border-route font-semibold text-ink" : "border-transparent text-steel hover:text-ink"}`}>
      {label}
    </button>
  );

  return (
    <div className="mx-auto max-w-[1280px] px-4 pb-16 sm:px-8">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-rule pt-6">
        <div className="flex items-end gap-8">
          <h1 className="display pb-2 text-[22px] font-bold">
            <span className="mr-2 inline-block h-3 w-3 rounded-[2px] bg-route align-middle" aria-hidden="true" />
            Ticket desk
          </h1>
          <nav className="flex gap-6">{tab("analyse", "Analyse")}{tab("history", "Audit log")}</nav>
        </div>
        <div className="pb-2.5"><Status /></div>
      </header>

      {view === "analyse" ? (
        <main className="mt-8 grid gap-10 md:grid-cols-[340px_minmax(0,1fr)]">
          <div className="md:sticky md:top-6 md:self-start"><TicketForm onSubmit={analyse} busy={busy} /></div>
          <div aria-live="polite">
            {error && (
              <div className="mb-6 border-l-4 border-stop bg-sheet px-4 py-3" role="alert">
                <p className="text-[15px] font-semibold text-stop">{error.message}</p>
                {error.requestId && <p className="mt-1 text-[13px] text-steel">Reference {error.requestId}</p>}
              </div>
            )}
            {busy && !result && <p className="pt-2 text-[15px] text-steel">Running the checks…</p>}
            {result ? <div className={busy ? "opacity-50" : ""}><Result result={result} /></div> : !busy && <Empty />}
          </div>
        </main>
      ) : (
        <main className="mt-8"><History /></main>
      )}
    </div>
  );
}

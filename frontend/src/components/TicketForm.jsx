// The analyst pastes a ticket here. The ticket text uses a serif face: it's the requester's own words.
import { useState } from "react";
import { SAMPLES } from "../lib/words";

const APPS = ["Active Directory", "GlobalProtect VPN", "Outlook", "Microsoft Teams", "SAP", "Salesforce",
  "HR Portal", "Microsoft 365", "Printer", "Laptop", "Corporate Wi-Fi", "Exchange Online"];
const EMPTY = { title: "", description: "", application: "", environment: "prod" };

export default function TicketForm({ onSubmit, busy }) {
  const [ticket, setTicket] = useState(EMPTY);
  const [error, setError] = useState("");
  const set = (k) => (e) => { setTicket({ ...ticket, [k]: e.target.value }); setError(""); };

  function submit(e) {
    e.preventDefault();
    if (!ticket.title.trim() || !ticket.description.trim()) {
      setError("Add a title and a description to analyse the ticket.");
      return;
    }
    onSubmit({ ...ticket, application: ticket.application || null });
  }

  return (
    <form onSubmit={submit} noValidate>
      <h2 className="display text-[26px] font-bold leading-tight">New ticket</h2>
      <p className="mt-1 text-[14px] text-steel">Paste what the requester wrote.</p>

      <label className="mt-5 block text-[14px] font-semibold" htmlFor="title">Title</label>
      <input id="title" className="field mt-1" maxLength={200} value={ticket.title} onChange={set("title")}
        placeholder="VPN not connecting from home" />

      <label className="mt-4 block text-[14px] font-semibold" htmlFor="description">Description</label>
      <textarea id="description" className="field mt-1 min-h-[180px] resize-y font-serif text-[16px] leading-relaxed"
        maxLength={5000} value={ticket.description} onChange={set("description")}
        placeholder="Since this morning GlobalProtect says my certificate is invalid…" />

      <div className="mt-4 grid grid-cols-[1fr_96px] gap-3">
        <div>
          <label className="block text-[14px] font-semibold" htmlFor="application">Application</label>
          <input id="application" list="apps" className="field mt-1" value={ticket.application} onChange={set("application")}
            placeholder="Optional" />
          <datalist id="apps">{APPS.map((a) => <option key={a} value={a} />)}</datalist>
        </div>
        <div>
          <label className="block text-[14px] font-semibold" htmlFor="environment">Where</label>
          <select id="environment" className="field mt-1" value={ticket.environment} onChange={set("environment")}>
            <option value="prod">Live</option>
            <option value="uat">Test</option>
          </select>
        </div>
      </div>

      {error && <p className="mt-3 text-[14px] text-stop" role="alert">{error}</p>}

      <button type="submit" className="btn-primary mt-5 w-full" disabled={busy}>
        {busy ? "Analysing…" : "Analyse ticket"}
      </button>

      <div className="mt-6 border-t border-rule pt-4">
        <p className="text-[14px] text-steel">Or load an example</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {SAMPLES.map((s) => (
            <button key={s.name} type="button" className="btn-quiet" disabled={busy}
              onClick={() => { setTicket({ ...s.ticket }); setError(""); }}>
              {s.name}
            </button>
          ))}
        </div>
      </div>
    </form>
  );
}

// Analyst verdict on a recommendation or on one matched record (brief FR-06).
import { useState } from "react";
import { api } from "../lib/api";

const VERDICTS = [
  { value: "useful", label: "Useful", done: "Marked useful" },
  { value: "incorrect", label: "Incorrect", done: "Marked incorrect" },
  { value: "unresolved", label: "Didn't resolve it", done: "Marked as not resolving it" },
];

export default function Feedback({ analysisId, target, disabled, compact = false }) {
  const [sent, setSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (disabled) return <p className="text-[13px] text-steel">Feedback is off because this result wasn&apos;t saved.</p>;
  if (sent) return <p className="text-[13px] text-go">{VERDICTS.find((v) => v.value === sent).done}</p>;

  async function send(verdict) {
    setBusy(true);
    setError("");
    try {
      await api.sendFeedback(analysisId, { verdict, target });
      setSent(verdict);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {!compact && <span className="mr-1 text-[13px] text-steel">Was this right?</span>}
      {VERDICTS.map((v) => (
        <button key={v.value} type="button" disabled={busy} onClick={() => send(v.value)}
          className="rounded-full border border-rule px-2.5 py-0.5 text-[13px] text-ink hover:border-steel disabled:opacity-50">
          {v.label}
        </button>
      ))}
      {error && <span className="text-[13px] text-stop" role="alert">{error}</span>}
    </div>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { History, MessageSquarePlus, Send } from "lucide-react";
import { MAX_NOTE_CHARS, VERDICTS, validateFeedback, type FeedbackErrors, type FeedbackInput } from "../../lib/feedback";
import { formatTimestamp, humanize } from "../../lib/format";
import { sortedCauses } from "../../lib/evidence";
import type { Diagnosis, FeedbackRecord } from "../../lib/types";
import { useAppData } from "../../state/AppData";
import { useToast } from "../../state/Toasts";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorAlert, LoadingBlock, Mono } from "../common/ui";

const EMPTY_INPUT: FeedbackInput = { verdict: "", causeId: "", note: "" };

export function FeedbackForm({ diagnosis, onSaved }: { diagnosis: Diagnosis; onSaved: (record: FeedbackRecord) => void }) {
  const { api } = useAppData();
  const { notify } = useToast();
  const [input, setInput] = useState<FeedbackInput>(EMPTY_INPUT);
  const [errors, setErrors] = useState<FeedbackErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const inFlight = useRef(false); // guards double clicks before React re-renders the disabled button
  const causes = useMemo(() => sortedCauses(diagnosis), [diagnosis]);
  const noCauses = causes.length === 0;

  useEffect(() => {
    setInput(EMPTY_INPUT);
    setErrors({});
    setSubmitError(null);
  }, [diagnosis.diagnosis_id]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (inFlight.current) return;
    const { errors: found, body } = validateFeedback(input, diagnosis);
    setErrors(found);
    setSubmitError(null);
    if (!body) return;
    inFlight.current = true;
    setSubmitting(true);
    try {
      const record = await api.addFeedback(diagnosis.diagnosis_id, body);
      notify(`Feedback saved: ${record.verdict}${record.cause_id ? ` on ${record.cause_id}` : " on the whole diagnosis"}.`);
      setInput(EMPTY_INPUT);
      onSaved(record);
    } catch (error) {
      setSubmitError(error);
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  const noteRequired = input.verdict === "annotate";
  return (
    <Card aria-labelledby="feedback-title">
      <CardHeader id="feedback-title" icon={<MessageSquarePlus className="h-5 w-5" />} title="Add reviewer feedback"
                  description="Feedback is appended to the audit log; earlier feedback is never changed." />
      <form onSubmit={submit} noValidate className="space-y-5 p-5">
        <fieldset aria-describedby={errors.verdict ? "verdict-error" : undefined}>
          <legend className="mb-2 text-sm font-medium text-ink">Verdict</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {VERDICTS.map((v) => (
              <label key={v.value}
                     className={`flex cursor-pointer flex-col rounded-lg border p-3 text-sm transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary ${
                       input.verdict === v.value ? "border-primary bg-primary-soft" : "border-slate-200 hover:bg-slate-50"}`}>
                <span className="flex items-center gap-2 font-medium">
                  <input type="radio" name="verdict" value={v.value} checked={input.verdict === v.value}
                         onChange={() => setInput((s) => ({ ...s, verdict: v.value }))} className="accent-primary" />
                  {v.label}
                </span>
                <span className="mt-1 text-xs text-muted">{v.help}</span>
              </label>
            ))}
          </div>
          {errors.verdict && <p id="verdict-error" className="mt-1.5 text-sm text-danger-text">{errors.verdict}</p>}
        </fieldset>

        <div>
          <label htmlFor="feedback-cause" className="mb-1.5 block text-sm font-medium text-ink">Cause (optional)</label>
          <select id="feedback-cause" value={input.causeId} disabled={noCauses}
                  onChange={(e) => setInput((s) => ({ ...s, causeId: e.target.value }))}
                  aria-invalid={Boolean(errors.causeId)} aria-describedby="cause-help"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:bg-slate-50">
            <option value="">Whole diagnosis</option>
            {causes.map((c) => <option key={c.cause} value={c.cause}>#{c.rank} {humanize(c.cause)} ({c.cause})</option>)}
          </select>
          <p id="cause-help" className={`mt-1 text-xs ${errors.causeId ? "text-danger-text" : "text-muted"}`}>
            {errors.causeId ?? (noCauses
              ? "This diagnosis claims no cause, so feedback applies to the whole diagnosis."
              : "Leave as “Whole diagnosis” to review the diagnosis as a whole.")}
          </p>
        </div>

        <div>
          <label htmlFor="feedback-note" className="mb-1.5 block text-sm font-medium text-ink">
            Note {noteRequired ? <span className="text-danger-text">(required)</span> : <span className="font-normal text-muted">(optional)</span>}
          </label>
          <textarea id="feedback-note" rows={4} value={input.note} maxLength={MAX_NOTE_CHARS}
                    onChange={(e) => setInput((s) => ({ ...s, note: e.target.value }))}
                    aria-invalid={Boolean(errors.note)} aria-describedby="note-help" aria-required={noteRequired}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                    placeholder="What did the first check show? Secrets in notes are masked by the backend." />
          <p id="note-help" className={`mt-1 flex justify-between text-xs ${errors.note ? "text-danger-text" : "text-muted"}`}>
            <span>{errors.note ?? "Plain text. The backend masks tokens, keys and emails before saving."}</span>
            <span aria-hidden>{input.note.length}/{MAX_NOTE_CHARS}</span>
          </p>
        </div>

        {errors.diagnosis && <p role="alert" className="text-sm text-danger-text">{errors.diagnosis}</p>}
        {submitError !== null && <ErrorAlert error={submitError} compact />}

        <Button type="submit" variant="primary" loading={submitting} loadingText="Saving feedback…"
                icon={<Send className="h-4 w-4" aria-hidden />}>
          Submit feedback
        </Button>
      </form>
    </Card>
  );
}

const verdictTone = { confirm: "success", reject: "danger", annotate: "primary" } as const;

export function FeedbackHistory({ diagnosisId, refreshKey }: { diagnosisId: string; refreshKey: number }) {
  const { api } = useAppData();
  const [records, setRecords] = useState<FeedbackRecord[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    const ctl = new AbortController();
    setLoading(true);
    setError(null);
    api.feedback(diagnosisId, ctl.signal)
      .then((r) => { if (!ctl.signal.aborted) setRecords(r); })
      .catch((e: unknown) => { if (!ctl.signal.aborted) setError(e); })
      .finally(() => { if (!ctl.signal.aborted) setLoading(false); });
    return () => ctl.abort();
  }, [api, diagnosisId, refreshKey, attempt]);

  return (
    <Card aria-labelledby="history-title">
      <CardHeader id="history-title" icon={<History className="h-5 w-5" />} title="Feedback history"
                  description="Oldest first, from GET /api/diagnoses/{id}/feedback." />
      {loading && !records ? <LoadingBlock label="Loading feedback history" /> : error ? (
        <div className="p-5"><ErrorAlert error={error} onRetry={retry} retrying={loading} /></div>
      ) : !records || records.length === 0 ? (
        <EmptyState title="No feedback yet">Be the first reviewer to confirm, reject or annotate this diagnosis.</EmptyState>
      ) : (
        <ol className="divide-y divide-slate-100" aria-label="Feedback records">
          {records.map((r) => (
            <li key={r.feedback_id} className="px-5 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={verdictTone[r.verdict as keyof typeof verdictTone] ?? "neutral"}>{humanize(r.verdict)}</Badge>
                <span className="text-slate-700">{r.cause_id ? <Mono>{r.cause_id}</Mono> : "Whole diagnosis"}</span>
                <span className="ml-auto text-xs text-muted">{formatTimestamp(r.created_at)}</span>
              </div>
              {r.note && <p className="mt-1.5 whitespace-pre-wrap text-slate-700">{r.note}</p>}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

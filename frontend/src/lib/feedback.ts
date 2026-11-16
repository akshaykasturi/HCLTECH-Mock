import type { Diagnosis, FeedbackRequest, Verdict } from "./types";

export const MAX_NOTE_CHARS = 2000; // same limit as the backend (audit.MAX_NOTE_CHARS)
export const MIN_ANNOTATION_CHARS = 3;
export const VERDICTS: { value: Verdict; label: string; help: string }[] = [
  { value: "confirm", label: "Confirm", help: "The first check proved this cause (or the whole diagnosis) right." },
  { value: "reject", label: "Reject", help: "The check showed this cause (or the diagnosis) is wrong." },
  { value: "annotate", label: "Annotate", help: "Add a note without a verdict. A note is required." },
];

export interface FeedbackInput {
  verdict: Verdict | "";
  causeId: string; // "" = whole diagnosis
  note: string;
}

export type FeedbackErrors = Partial<Record<"verdict" | "causeId" | "note" | "diagnosis", string>>;

/** Client-side checks that mirror the backend's: returns field errors, or the request body to send. */
export function validateFeedback(input: FeedbackInput, diagnosis: Pick<Diagnosis, "diagnosis_id" | "ranked"> | null):
  { errors: FeedbackErrors; body: FeedbackRequest | null } {
  const errors: FeedbackErrors = {};
  if (!diagnosis?.diagnosis_id) errors.diagnosis = "Feedback needs a saved diagnosis.";
  if (!input.verdict) errors.verdict = "Choose confirm, reject or annotate.";
  const note = input.note.trim();
  if (input.verdict === "annotate" && note.length < MIN_ANNOTATION_CHARS) {
    errors.note = "An annotation needs a note (at least 3 characters).";
  }
  if (note.length > MAX_NOTE_CHARS) errors.note = `Keep the note under ${MAX_NOTE_CHARS} characters.`;
  if (input.causeId) {
    // cause_id must be a ranked[].cause of this diagnosis (the backend checks it too). Never the rank.
    const known = new Set((diagnosis?.ranked ?? []).map((c) => c.cause));
    if (!known.has(input.causeId)) errors.causeId = "Choose a cause from this diagnosis, or the whole diagnosis.";
  }
  if (Object.keys(errors).length > 0) return { errors, body: null };
  const body: FeedbackRequest = { verdict: input.verdict as Verdict };
  if (input.causeId) body.cause_id = input.causeId;
  if (note) body.note = note;
  return { errors, body };
}

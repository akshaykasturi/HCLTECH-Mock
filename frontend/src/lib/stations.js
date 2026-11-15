// Turns an analysis result (its trace and signals) into the six stations drawn by RouteTrack.
import { generatorText, reasonText } from "./words";

export const NAMES = ["Hide personal data", "Classify", "Find past cases", "Safety and evidence check", "Write steps", "Check quotes"];

export function buildStations(result) {
  const step = (name) => result.trace?.find((e) => e.step === name)?.detail || {};
  const signals = result.signals || {};
  const values = Object.entries(signals);
  const weakest = values.length ? values.reduce((a, b) => (b[1] < a[1] ? b : a))[0] : null;
  const gate = step("gate");
  const stopped = Boolean(gate.stopped);
  const stopTone = gate.stopped === "CLARIFY" ? "hold" : "stop";
  const red = step("redact").redactions || result.redactions || {};
  const hidden = Object.entries(red).map(([k, n]) => `${n} ${k}${n > 1 ? "s" : ""}`);
  const verify = step("verify");
  const gen = step("generate");
  const cls = result.classification || {};

  return [
    { name: NAMES[0], state: "done", text: hidden.length ? `Hid ${hidden.join(", ")}` : "Nothing to hide" },
    {
      name: NAMES[1], state: "done",
      text: `${cls.category} / ${cls.subcategory}, priority ${cls.priority}`,
      meter: signals.classifier, signal: "classifier",
    },
    {
      name: NAMES[2], state: "done",
      text: result.matches?.length
        ? `${result.matches.length} similar records, best ${result.matches[0].source_id}`
        : "No similar records",
      meter: signals.retrieval, signal: "retrieval",
    },
    {
      name: NAMES[3], state: stopped ? "stopped" : "done", tone: stopTone,
      text: stopped
        ? (gate.reasons || []).map(reasonText).join(". ")
        : "Passed. Safe to draft steps from the evidence.",
    },
    {
      name: NAMES[4], state: stopped ? "skipped" : "done",
      text: stopped ? "Not run" : generatorText(gen.generator) + (gen.fallback ? `. ${reasonText(gen.fallback)}` : ""),
      note: !stopped && gen.llm_errors?.length ? `Skipped: ${gen.llm_errors.map((e) => e.split(":")[0]).join(", ")}` : null,
    },
    {
      name: NAMES[5], state: stopped ? "skipped" : "done",
      text: stopped ? "Not run" : `${verify.kept ?? 0} quote${verify.kept === 1 ? "" : "s"} matched the source` +
        (verify.dropped ? `, ${verify.dropped} removed` : ""),
      meter: stopped ? undefined : signals.grounding, signal: "grounding",
    },
  ].map((s) => ({ ...s, weakest: s.signal === weakest && s.meter !== undefined }));
}


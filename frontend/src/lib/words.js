// Plain-language text for everything the backend sends as a code. Analysts should never read raw codes.

export const OUTCOME = {
  RECOMMEND: { label: "Recommended fix", color: "go", hint: "Evidence supports these steps. Review before acting." },
  CLARIFY: { label: "Needs more detail", color: "hold", hint: "Ask the requester for more information before acting." },
  ESCALATE: { label: "Escalate to a person", color: "stop", hint: "No reliable answer from past cases. Hand this to an engineer." },
};

export function reasonText(code) {
  if (code.startsWith("CITATIONS_DROPPED:")) {
    const n = code.split(":")[1];
    return `${n} quote${n === "1" ? "" : "s"} removed because ${n === "1" ? "it" : "they"} didn't match the source`;
  }
  if (code.startsWith("LLM_FAILED")) return "AI writer unavailable, steps copied from past cases";
  return (
    {
      SAFETY_KEYWORD: "Possible safety hazard mentioned",
      INJECTION_SUSPECTED: "Ticket contains instructions aimed at the system",
      LOW_RETRIEVAL_SCORE: "No closely matching past case",
      TOO_VAGUE: "Too little detail to analyse",
      NO_VERIFIED_CITATION: "No step could be traced to a source",
      LOW_CLASSIFIER_CONFIDENCE: "Category is uncertain",
      LLM_NO_STEPS: "AI writer found the evidence didn't fit, steps copied from past cases",
      AUDIT_WRITE_FAILED: "Result not saved to the audit log",
    }[code] || code
  );
}

export function generatorText(generator) {
  if (!generator) return "Not generated";
  if (generator === "extractive") return "Copied from past cases";
  const [provider, model] = generator.split(":");
  const name = { gemini: "Gemini", groq: "Groq", fake: "Test writer" }[provider] || provider;
  return model ? `${name} (${model})` : name;
}

export const pct = (x) => `${Math.round((x ?? 0) * 100)}%`;

export function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Demo tickets: one per outcome, so the whole flow can be shown in under a minute.
export const SAMPLES = [
  {
    name: "VPN certificate",
    ticket: {
      title: "VPN not connecting from home",
      description:
        "Since this morning GlobalProtect says the client certificate is invalid and won't connect. It worked fine last week. Reach me at priya.nair@acmecorp.example if you need anything.",
      application: "GlobalProtect VPN",
      environment: "prod",
    },
  },
  {
    name: "Burning printer",
    ticket: {
      title: "Printer smells strange",
      description: "The printer on floor 3 smells like burning plastic and there is a little smoke coming out of the back.",
      application: "",
      environment: "prod",
    },
  },
  {
    name: "Vague request",
    ticket: { title: "Help", description: "It's not working.", application: "", environment: "prod" },
  },
];

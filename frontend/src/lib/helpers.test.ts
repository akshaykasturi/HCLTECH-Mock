import { describe, expect, it } from "vitest";
import { formatConfidence, generatorLabel, humanize, splitRoute, valueToText } from "./format";
import { validateFeedback } from "./feedback";
import { causeEvidenceIds, kindLabel, sortedCauses, unresolvedIds } from "./evidence";
import { deriveHealth } from "./health";
import { ApiError } from "./api";
import { clarifyDiagnosis, recommendDiagnosis } from "../test/fixtures";

describe("confidence formatting (Akshay's rule)", () => {
  it.each([
    [0.997203, "> 0.99"], [0.9901, "> 0.99"], [0.99, "0.99"], [0.5, "0.50"], [0.0204, "0.02"],
    [0.01, "0.01"], [0.0099, "< 0.01"], [0, "< 0.01"], [null, "—"],
  ])("%s -> %s", (value, expected) => {
    expect(formatConfidence(value)).toBe(expected);
  });

  it("does not change the value it formats", () => {
    const d = recommendDiagnosis();
    formatConfidence(d.class_confidence);
    expect(d.class_confidence).toBe(0.997203);
  });
});

describe("format helpers", () => {
  it("labels the generator truthfully", () => {
    expect(generatorLabel("template")).toBe("Written by template");
    expect(generatorLabel("gemini")).toBe("Written by gemini");
  });
  it("humanizes ids and splits routes", () => {
    expect(humanize("token_expired")).toBe("Token expired");
    expect(splitRoute("GET /v1/orders/{id}")).toEqual({ method: "GET", path: "/v1/orders/{id}" });
  });
  it("renders data values as plain text", () => {
    expect(valueToText({ a: 1 })).toContain('"a": 1');
    expect(valueToText("<b>x</b>")).toBe("<b>x</b>");
  });
});

describe("evidence helpers", () => {
  it("sorts causes by rank", () => {
    expect(sortedCauses(recommendDiagnosis()).map((c) => c.rank)).toEqual([1, 2, 3, 4, 5, 6]);
  });
  it("collects supporting and contradicting evidence ids", () => {
    const top = sortedCauses(recommendDiagnosis())[0];
    expect(causeEvidenceIds(top)).toEqual({ supporting: ["request:c-4261adc1ef"], contradicting: ["metric:service:auth"] });
  });
  it("finds cited ids that are not in the evidence list", () => {
    const d = recommendDiagnosis();
    expect(unresolvedIds(d)).toEqual([]);
    d.ranked[0].supporting[0].evidence_ids.push("metric:ghost");
    expect(unresolvedIds(d)).toEqual(["metric:ghost"]);
  });
  it("names unknown evidence kinds by themselves", () => {
    expect(kindLabel("metric")).toBe("Metric");
    expect(kindLabel("runbook")).toBe("runbook");
  });
});

describe("feedback validation", () => {
  const d = recommendDiagnosis();
  it("requires a verdict", () => {
    expect(validateFeedback({ verdict: "", causeId: "", note: "" }, d).errors.verdict).toBeDefined();
  });
  it("allows whole-diagnosis feedback without cause_id", () => {
    expect(validateFeedback({ verdict: "confirm", causeId: "", note: "" }, d).body).toEqual({ verdict: "confirm" });
  });
  it("sends the cause name, never the rank", () => {
    const { body } = validateFeedback({ verdict: "reject", causeId: "invalid_api_key", note: " checked " }, d);
    expect(body).toEqual({ verdict: "reject", cause_id: "invalid_api_key", note: "checked" });
  });
  it("rejects a cause that is not ranked in this diagnosis", () => {
    expect(validateFeedback({ verdict: "confirm", causeId: "2", note: "" }, d).errors.causeId).toBeDefined();
    expect(validateFeedback({ verdict: "confirm", causeId: "dns_failure", note: "" }, d).body).toBeNull();
  });
  it("needs a meaningful note to annotate", () => {
    expect(validateFeedback({ verdict: "annotate", causeId: "", note: "  " }, d).errors.note).toBeDefined();
    expect(validateFeedback({ verdict: "annotate", causeId: "", note: "ok" }, d).errors.note).toBeDefined();
    expect(validateFeedback({ verdict: "annotate", causeId: "", note: "Checked token" }, d).body).not.toBeNull();
  });
  it("cannot send feedback without a saved diagnosis", () => {
    expect(validateFeedback({ verdict: "confirm", causeId: "", note: "" }, null).errors.diagnosis).toBeDefined();
  });
  it("on CLARIFY no cause can be chosen", () => {
    expect(validateFeedback({ verdict: "confirm", causeId: "token_expired", note: "" }, clarifyDiagnosis()).body).toBeNull();
  });
});

describe("health states", () => {
  it("maps backend values without guessing", () => {
    expect(deriveHealth({ api: "up", database: "down", pipeline: "not_ready", pipeline_detail: "" }, null))
      .toEqual({ api: "healthy", database: "unavailable", pipeline: "not_ready" });
    expect(deriveHealth(null, new ApiError("network", "NETWORK_ERROR", "x")))
      .toEqual({ api: "unavailable", database: "unknown", pipeline: "unknown" });
    expect(deriveHealth(null, null)).toEqual({ api: "unknown", database: "unknown", pipeline: "unknown" });
  });
});

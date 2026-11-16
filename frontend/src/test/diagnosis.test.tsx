import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { createApiClient, makeEndpoints, PIPELINE_NOT_READY_MESSAGE } from "../lib/api";
import { deferred, fail, mockBackend, ok, renderApp, type Reply } from "./utils";
import { clarifyDiagnosis, closeCallDiagnosis, escalateDiagnosis, recommendDiagnosis } from "./fixtures";

async function runDiagnosis(path = "/diagnosis/UC4-0001") {
  const view = renderApp(path);
  await view.user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
  return view;
}

describe("diagnosis workspace", () => {
  it("sends POST /api/diagnose with the case_id", async () => {
    const backend = mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis(), 201) });
    await runDiagnosis();
    await screen.findByRole("heading", { name: "Recommendation" });
    expect(backend.callsTo("POST", "/api/diagnose")).toEqual([{ method: "POST", path: "/api/diagnose", body: { case_id: "UC4-0001" } }]);
  });

  it("shows a loading state and prevents duplicate submissions", async () => {
    const gate = deferred<Reply>();
    const backend = mockBackend({ "POST /api/diagnose": () => gate.promise });
    const { user } = renderApp("/diagnosis/UC4-0001");
    const headerButton = await screen.findByRole("button", { name: "Run diagnosis" });
    await user.click(headerButton);
    const busy = screen.getByRole("button", { name: "Diagnosing…" });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText(/Collecting evidence, ranking causes/)).toBeInTheDocument();
    await user.click(busy);
    await user.dblClick(busy);
    expect(backend.callsTo("POST", "/api/diagnose")).toHaveLength(1);
    gate.resolve(ok(recommendDiagnosis(), 201));
    await screen.findByRole("heading", { name: "Recommendation" });
    expect(backend.callsTo("POST", "/api/diagnose")).toHaveLength(1);
  });

  it("renders a RECOMMEND diagnosis with ranked causes sorted by rank", async () => {
    mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis(), 201) });
    await runDiagnosis();
    const banner = (await screen.findByRole("heading", { name: "Recommendation" })).closest("section")!;
    expect(within(banner).getByText("RECOMMEND")).toBeInTheDocument();
    expect(within(banner).getByText("Token expired")).toBeInTheDocument();
    expect(within(banner).queryByText("Escalate")).not.toBeInTheDocument();
    const list = within(screen.getByRole("region", { name: "Ranked causes" })).getAllByRole("listitem")
      .filter((li) => li.getAttribute("aria-label")?.startsWith("Rank"));
    expect(list.map((li) => li.getAttribute("aria-label"))).toEqual([
      "Rank 1: token_expired", "Rank 2: invalid_api_key", "Rank 3: client_timeout_too_low",
      "Rank 4: missing_scope", "Rank 5: ip_not_allowlisted"]);
    expect(screen.getByRole("button", { name: "Show all 6 causes" })).toBeInTheDocument();
    expect(await screen.findByText(/Diagnosis saved for UC4-0001: RECOMMEND/)).toBeInTheDocument(); // toast
  });

  it("formats confidence with the > 0.99 / < 0.01 rule and never says confirmed", async () => {
    mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis(), 201) });
    await runDiagnosis();
    const ranked = await screen.findByRole("region", { name: "Ranked causes" });
    expect(within(ranked).getByRole("meter", { name: "Confidence for token_expired" })).toHaveAttribute("aria-valuetext", "0.98");
    expect(within(ranked).getByRole("meter", { name: "Confidence for invalid_api_key" })).toHaveAttribute("aria-valuetext", "0.02");
    expect(within(ranked).getByRole("meter", { name: "Confidence for client_timeout_too_low" })).toHaveAttribute("aria-valuetext", "< 0.01");
    expect(screen.getByText("(> 0.99)")).toBeInTheDocument(); // class_confidence 0.997203
    expect(within(ranked).getByText("Likely")).toBeInTheDocument();
    // Every cause status badge is one of the three allowed labels; "Confirmed" is never a status.
    const statuses = within(ranked).getAllByText(/^(Likely|Probable|Unsupported|Unrated|Confirmed)$/).map((el) => el.textContent);
    expect(statuses).not.toContain("Confirmed");
    expect(new Set(statuses)).toEqual(new Set(["Likely", "Unsupported"]));
    expect(screen.queryByText(/^confirmed$/i)).not.toBeInTheDocument();
  });

  it("an unknown cause status is shown as Unrated, never as confirmed", async () => {
    const d = recommendDiagnosis();
    d.ranked[1] = { ...d.ranked[1], status: "confirmed" };
    mockBackend({ "POST /api/diagnose": ok(d, 201) });
    await runDiagnosis();
    const ranked = await screen.findByRole("region", { name: "Ranked causes" });
    expect(within(ranked).getByText("Unrated")).toBeInTheDocument();
    expect(within(ranked).queryByText(/^confirmed$/i)).not.toBeInTheDocument();
  });

  it("expands a cause's supporting and contradicting signals with evidence links", async () => {
    mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis(), 201) });
    const { user } = await runDiagnosis();
    const top = await screen.findByRole("listitem", { name: "Rank 1: token_expired" });
    await user.click(within(top).getByRole("button", { name: /Show signals/ }));
    expect(within(top).getByText("token_age_over_ttl")).toBeInTheDocument();
    expect(within(top).getByText("×4.0")).toBeInTheDocument();
    expect(within(top).getByRole("link", { name: "request:c-4261adc1ef" })).toHaveAttribute(
      "href", "/evidence?d=dx-recommend-1&focus=request%3Ac-4261adc1ef");
    expect(within(top).getByRole("link", { name: "metric:service:auth" })).toBeInTheDocument();
    expect(within(top).getByText("expected but absent")).toBeInTheDocument();
    expect(within(top).getByText("check_token_expiry")).toBeInTheDocument();
  });

  it("renders CLARIFY with a null report and missing information first", async () => {
    mockBackend({ "POST /api/diagnose": ok(clarifyDiagnosis(), 201) });
    await runDiagnosis("/diagnosis/UC4-0085");
    expect(await screen.findByRole("heading", { name: "More information needed" })).toBeInTheDocument();
    expect(screen.getByText("CLARIFY")).toBeInTheDocument();
    const missing = screen.getByRole("region", { name: "Missing information" });
    expect(within(missing).getByText("Metrics for orders-db around the onset")).toBeInTheDocument();
    expect(screen.getByText("No ranked causes")).toBeInTheDocument();
    expect(screen.getByText("No report for this diagnosis")).toBeInTheDocument();
    expect(screen.queryByText("Recommendation")).not.toBeInTheDocument();
  });

  it("shows escalation as a flag with the report's team and reason", async () => {
    mockBackend({ "POST /api/diagnose": ok(escalateDiagnosis(), 201) });
    await runDiagnosis("/diagnosis/UC4-0019");
    const banner = (await screen.findByRole("heading", { name: "Recommendation" })).closest("section")!;
    expect(within(banner).getByText("RECOMMEND")).toBeInTheDocument();
    expect(within(banner).getByText("Escalate")).toBeInTheDocument();
    expect(screen.queryByText("ESCALATE")).not.toBeInTheDocument();
    const escalation = screen.getByRole("region", { name: "Escalation" });
    expect(within(escalation).getByText("Escalation needed")).toBeInTheDocument();
    expect(within(escalation).getByText("payments-api owners")).toBeInTheDocument();
    expect(within(escalation).getByText(/check_ip_allowlist needs privileged access/)).toBeInTheDocument();
    expect(screen.getByText("Privileged check")).toBeInTheDocument();
  });

  it("shows the report summary, verification steps, citations and the template generator", async () => {
    mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis(), 201) });
    await runDiagnosis();
    const report = await screen.findByRole("region", { name: "Report" });
    expect(within(report).getByText("Written by template")).toBeInTheDocument();
    expect(within(report).getByText(/the access token was older than its lifetime/)).toBeInTheDocument();
    expect(within(report).getByText("Decode the token and compare exp with the request time.")).toBeInTheDocument();
    expect(within(report).getByText("“token age 4000 s (ttl 3600 s)”")).toBeInTheDocument();
    expect(within(report).getAllByRole("link", { name: "request:c-4261adc1ef" }).length).toBe(2);
    expect(within(report).getByText("No escalation needed")).toBeInTheDocument();
    expect(screen.queryByText(/LLM|gemini|groq/i)).not.toBeInTheDocument();
  });

  it("shows checks, groundedness and the decision trace", async () => {
    mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis({
      report_findings: [{ code: "CITE_QUOTE_NOT_FOUND", severity: "warn", message: "A quote was not found.", where: "causes[0]" }],
      groundedness: 0.5,
    }), 201) });
    const { user } = await runDiagnosis();
    const checks = await screen.findByRole("region", { name: "Report checks" });
    expect(within(checks).getByText("CITE_QUOTE_NOT_FOUND")).toBeInTheDocument();
    expect(within(checks).getByText("0.50")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show 3 steps" }));
    const trace = screen.getByRole("region", { name: "How this was decided" });
    expect(within(trace).getByText("collect_evidence")).toBeInTheDocument();
    expect(within(trace).getByText("157 ms")).toBeInTheDocument();
    expect(within(trace).getByText("3 items, 0 missing")).toBeInTheDocument();
  });

  it("shows the close-call analysis", async () => {
    mockBackend({ "POST /api/diagnose": ok(closeCallDiagnosis(), 201) });
    await runDiagnosis("/diagnosis/UC4-0006");
    const close = await screen.findByRole("region", { name: "Close call: how to tell them apart" });
    expect(within(close).getByText("Check the token age first: it separates the two causes best.")).toBeInTheDocument();
    expect(within(close).getByText("check_key_registry")).toBeInTheDocument();
    expect(within(close).getByText("token_age_over_ttl")).toBeInTheDocument();
    expect(within(close).getByText("0.90")).toBeInTheDocument();
    expect(within(close).getByText("Unknown")).toBeInTheDocument();
    expect(screen.getAllByText("Near tie").length).toBe(2);
  });

  it.each([
    [404, "CASE_NOT_FOUND", "Case not found"],
    [422, "VALIDATION_ERROR", "Invalid request"],
    [500, "INTERNAL_ERROR", "Server error"],
    [502, "DIAGNOSIS_FAILED", "Diagnosis failed"],
    [502, "DIAGNOSIS_INVALID", "Diagnosis rejected"],
    [504, "DIAGNOSIS_TIMEOUT", "Diagnosis timed out"],
  ])("handles HTTP %i %s without inventing a result", async (status, code, title) => {
    mockBackend({ "POST /api/diagnose": fail(status, code, "case_id: String should match pattern") });
    await runDiagnosis();
    expect(await screen.findByRole("alert")).toHaveTextContent(title);
    expect(screen.queryByRole("region", { name: "Ranked causes" })).not.toBeInTheDocument();
    expect(screen.queryByText("RECOMMEND")).not.toBeInTheDocument();
  });

  it("HTTP 503 shows the pipeline-not-ready message and a retry that works", async () => {
    let ready = false;
    const backend = mockBackend({ "POST /api/diagnose": () => (ready ? ok(recommendDiagnosis(), 201)
      : fail(503, "DIAGNOSIS_NOT_READY", "The diagnosis service is not ready yet.")) });
    const { user } = await runDiagnosis();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(PIPELINE_NOT_READY_MESSAGE);
    expect(screen.queryByRole("region", { name: "Ranked causes" })).not.toBeInTheDocument();
    ready = true;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Recommendation" })).toBeInTheDocument();
    expect(backend.callsTo("POST", "/api/diagnose")).toHaveLength(2);
  });

  it("handles a network timeout", async () => {
    mockBackend({ "POST /api/diagnose": "hang" });
    const endpoints = makeEndpoints(createApiClient({ baseUrl: "" }), { diagnoseTimeoutMs: 50 });
    const { user } = renderApp("/diagnosis/UC4-0001", { endpoints });
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Request timed out");
    expect(screen.getByRole("button", { name: "Run diagnosis" })).toBeEnabled();
  });

  it("handles the backend being unreachable", async () => {
    mockBackend({ "POST /api/diagnose": "network" });
    await runDiagnosis();
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unreachable");
  });

  it("warns for a case that is not in the case list and still lets the backend decide", async () => {
    mockBackend({ "POST /api/diagnose": fail(404, "CASE_NOT_FOUND", "The requested case was not found.") });
    await runDiagnosis("/diagnosis/UC4-9999");
    expect(screen.getByText("This case is not in the backend's case list.")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Case not found");
  });

  it("chooses a case from the picker", async () => {
    mockBackend();
    const { user } = renderApp("/diagnosis");
    const select = await screen.findByLabelText("Case");
    await waitFor(() => expect(select).toBeEnabled());
    await user.selectOptions(select, "UC4-0005");
    await user.click(screen.getByRole("button", { name: "Open workspace" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Diagnosis workspace · UC4-0005" })).toBeInTheDocument();
  });

  it("loads a saved diagnosis by id without re-running the pipeline", async () => {
    const backend = mockBackend({ "GET /api/diagnoses/dx-escalate-1": ok(escalateDiagnosis()) });
    renderApp("/diagnoses/dx-escalate-1");
    expect(await screen.findByRole("heading", { level: 1, name: "Diagnosis · UC4-0019" })).toBeInTheDocument();
    expect(screen.getByText("Escalation needed")).toBeInTheDocument();
    expect(backend.callsTo("POST", "/api/diagnose")).toHaveLength(0);
  });

  it("shows not found for a missing saved diagnosis", async () => {
    mockBackend({ "GET /api/diagnoses/dx-nope": fail(404, "DIAGNOSIS_NOT_FOUND", "The requested diagnosis was not found.") });
    renderApp("/diagnoses/dx-nope");
    expect(await screen.findByRole("alert")).toHaveTextContent("Diagnosis not found");
  });
});

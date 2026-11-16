// LIVE integration checks: the real React app, rendered in jsdom, talking to the real FastAPI backend
// through the Vite dev proxy. Opt-in only (needs a running backend + `npm run dev`):
//   PowerShell:  $env:VITE_LIVE_API_URL = "http://127.0.0.1:5173"; npx vitest --run src/live
// Nothing here is mocked. Outcomes are asserted only where the real pipeline is known to produce them
// (UC4-0001 RECOMMEND, UC4-0019 escalate, UC4-0085 CLARIFY, UC4-0006 close call); the UI itself never hardcodes them.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { createApiClient, makeEndpoints } from "../lib/api";
import { renderApp } from "../test/utils";

const BASE = import.meta.env.VITE_LIVE_API_URL as string | undefined;
const SLOW = { timeout: 30_000 };

/**
 * Test-environment adapter only: under jsdom, AbortController is jsdom's, and Node's real fetch rejects its
 * signal ("Expected signal to be an instance of AbortSignal"). Browsers have one native AbortController, so
 * the app does not need this. Cancellation still works: the request is raced against the jsdom signal.
 */
const liveFetch: typeof fetch = (input, init = {}) => {
  const { signal, ...rest } = init;
  const request = fetch(input, rest);
  if (!signal) return request;
  return new Promise<Response>((resolve, reject) => {
    if (signal.aborted) reject(new DOMException("Aborted", "AbortError"));
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    request.then(resolve, reject);
  });
};

describe.skipIf(!BASE)("live backend via the Vite proxy", () => {
  const endpoints = () => makeEndpoints(createApiClient({ baseUrl: BASE, fetchImpl: liveFetch }));
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => { consoleError = vi.spyOn(console, "error"); });
  afterEach(() => { expect(consoleError, "unexpected console.error during the live run").not.toHaveBeenCalled(); });

  async function run(caseId: string) {
    const view = renderApp(`/diagnosis/${caseId}`, { endpoints: endpoints() });
    await view.user.click(await screen.findByRole("button", { name: "Run diagnosis" }, SLOW));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Diagnosing…" })).not.toBeInTheDocument(), SLOW);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    return view;
  }

  it("dashboard shows the real case count and health", async () => {
    renderApp("/", { endpoints: endpoints() });
    expect(await screen.findByTestId("total-cases", {}, SLOW)).toHaveTextContent("90");
    await waitFor(() => expect(screen.getAllByText("Healthy")).toHaveLength(2), SLOW);
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
  }, 40_000);

  it("system health matches GET /health and /health/ready", async () => {
    renderApp("/system-health", { endpoints: endpoints() });
    for (const tile of ["API", "Audit database", "Diagnosis pipeline", "Readiness"]) {
      await waitFor(() => expect(within(screen.getByRole("article", { name: tile })).getByText("Healthy")).toBeInTheDocument(), SLOW);
    }
  }, 40_000);

  it("UC4-0001: RECOMMEND with ranked causes, resolved evidence and a template report", async () => {
    const { user } = await run("UC4-0001");
    const banner = screen.getByRole("heading", { name: "Recommendation" }).closest("section")!;
    expect(within(banner).getByText("RECOMMEND")).toBeInTheDocument();
    expect(within(banner).queryByText("Escalate")).not.toBeInTheDocument();
    const ranked = screen.getByRole("region", { name: "Ranked causes" });
    const items = within(ranked).getAllByRole("listitem").filter((li) => li.getAttribute("aria-label")?.startsWith("Rank"));
    expect(items[0].getAttribute("aria-label")).toMatch(/^Rank 1: /);
    expect(screen.queryByRole("note")).not.toBeInTheDocument(); // every cited evidence id resolved
    expect(within(screen.getByRole("region", { name: "Report" })).getByText("Written by template")).toBeInTheDocument();
    await user.click(within(items[0]).getByRole("button", { name: /Show signals/ }));
    const link = within(items[0]).getAllByRole("link")[0];
    const evidenceId = link.textContent!;
    await user.click(link);
    const card = await screen.findByRole("listitem", { name: `Evidence ${evidenceId}` });
    await waitFor(() => expect(card).toHaveFocus());
  }, 60_000);

  it("UC4-0019: escalate flag with the report's escalation details", async () => {
    await run("UC4-0019");
    const banner = screen.getByRole("heading", { name: "Recommendation" }).closest("section")!;
    expect(within(banner).getByText("Escalate")).toBeInTheDocument();
    const escalation = screen.getByRole("region", { name: "Escalation" });
    expect(within(escalation).getByText("Escalation needed")).toBeInTheDocument();
    expect(within(escalation).getByText(/Team:/)).toBeInTheDocument();
  }, 60_000);

  it("UC4-0085: CLARIFY with no ranked causes and missing information", async () => {
    await run("UC4-0085");
    expect(screen.getByRole("heading", { name: "More information needed" })).toBeInTheDocument();
    expect(screen.getByText("No ranked causes")).toBeInTheDocument();
    const missing = screen.getByRole("region", { name: "Missing information" });
    expect(within(missing).getAllByRole("listitem").length).toBeGreaterThan(0);
  }, 60_000);

  it("UC4-0006: close call with how to tell the causes apart", async () => {
    await run("UC4-0006");
    expect(screen.getByRole("region", { name: "Close call: how to tell them apart" })).toBeInTheDocument();
  }, 60_000);

  it("feedback round trip: cause feedback, whole-diagnosis feedback, history and audit chain", async () => {
    const { user } = await run("UC4-0001");
    await user.click(screen.getByRole("link", { name: "Review this diagnosis" }));
    await screen.findByText("No feedback yet", {}, SLOW);
    const select = screen.getByLabelText("Cause (optional)") as HTMLSelectElement;
    const secondCause = select.options[2].value; // a ranked[].cause name, not a rank
    await user.click(screen.getByRole("radio", { name: /Reject/ }));
    await user.selectOptions(select, secondCause);
    await user.type(screen.getByLabelText(/Note/), "Live check: key registry shows the key is valid.");
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(await screen.findByText(`Feedback saved: reject on ${secondCause}.`, {}, SLOW)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Confirm/ }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(await screen.findByText("Feedback saved: confirm on the whole diagnosis.", {}, SLOW)).toBeInTheDocument();
    const history = await screen.findByRole("list", { name: "Feedback records" }, SLOW);
    await waitFor(() => expect(within(history).getAllByRole("listitem")).toHaveLength(2), SLOW);
    await user.click(within(screen.getByRole("navigation", { name: "Main navigation" })).getByRole("link", { name: "Audit History" }));
    await user.click(await screen.findByRole("button", { name: "Verify chain" }));
    expect(await screen.findByText("Chain verified", {}, SLOW)).toBeInTheDocument();
  }, 90_000);

  it("an unknown case returns the backend's 404 in the UI", async () => {
    const { user } = renderApp("/diagnosis/UC4-9999", { endpoints: endpoints() });
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    expect(await screen.findByRole("alert", {}, SLOW)).toHaveTextContent("Case not found");
  }, 40_000);
});

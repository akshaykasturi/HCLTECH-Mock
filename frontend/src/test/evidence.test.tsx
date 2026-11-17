import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { mockBackend, ok, renderApp } from "./utils";
import { clarifyDiagnosis, recommendDiagnosis } from "./fixtures";
import type { Diagnosis } from "../lib/types";

function openEvidence(d: Diagnosis, extra = "") {
  mockBackend({ [`GET /api/diagnoses/${d.diagnosis_id}`]: ok(d) });
  return renderApp(`/evidence?d=${d.diagnosis_id}${extra}`);
}
const cards = () => screen.getAllByRole("listitem").filter((li) => li.getAttribute("aria-label")?.startsWith("Evidence "));

describe("evidence explorer", () => {
  it("lists evidence with kind badges and filters by category", async () => {
    const { user } = openEvidence(recommendDiagnosis());
    await screen.findByText("3 of 3 items");
    const filters = screen.getByRole("group", { name: "Filter by evidence kind" });
    for (const label of ["Request · 1", "Traffic · 1", "Metric · 1"]) {
      expect(within(filters).getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "false");
    }
    await user.click(within(filters).getByRole("button", { name: "Metric · 1" }));
    expect(within(filters).getByRole("button", { name: "Metric · 1" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("1 of 3 items")).toBeInTheDocument();
    expect(cards().map((c) => c.getAttribute("aria-label"))).toEqual(["Evidence metric:service:auth"]);
  });

  it("searches evidence text", async () => {
    const { user } = openEvidence(recommendDiagnosis());
    await screen.findByText("3 of 3 items");
    await user.type(screen.getByLabelText("Search evidence"), "40% errors");
    expect(cards().map((c) => c.getAttribute("aria-label"))).toEqual(["Evidence traffic:window"]);
  });

  it("groups supporting, contradicting and missing evidence for a cause", async () => {
    const { user } = openEvidence(recommendDiagnosis());
    await screen.findByText("3 of 3 items");
    await user.selectOptions(screen.getByLabelText("Group evidence by cause"), "token_expired");
    const supporting = screen.getByRole("region", { name: "Supporting evidence" });
    expect(within(supporting).getByRole("listitem", { name: "Evidence request:c-4261adc1ef" })).toBeInTheDocument();
    const contradicting = screen.getByRole("region", { name: "Contradicting evidence" });
    expect(within(contradicting).getByRole("listitem", { name: "Evidence metric:service:auth" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Missing evidence" })).getByText("Nothing missing.")).toBeInTheDocument();
  });

  it("shows which causes each item supports or contradicts", async () => {
    openEvidence(recommendDiagnosis());
    const card = await screen.findByRole("listitem", { name: "Evidence request:c-4261adc1ef" });
    expect(within(card).getByText("supports token_expired")).toBeInTheDocument();
    expect(within(card).getByText("supports invalid_api_key")).toBeInTheDocument();
  });

  it("expands and collapses evidence details as plain text", async () => {
    const { user } = openEvidence(recommendDiagnosis());
    const card = await screen.findByRole("listitem", { name: "Evidence traffic:window" });
    const toggle = within(card).getByRole("button", { name: "Show details (2 fields)" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(within(card).getByRole("button", { name: "Hide details" })).toHaveAttribute("aria-expanded", "true");
    expect(within(card).getByText("baseline_minutes")).toBeInTheDocument();
    expect(within(card).getByText(/"requests": 120/)).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Hide details" }));
    expect(within(card).queryByText("baseline_minutes")).not.toBeInTheDocument();
  });

  it("follows a citation: the cited card is focused, highlighted and expanded", async () => {
    openEvidence(recommendDiagnosis(), "&focus=metric%3Aservice%3Aauth");
    const card = await screen.findByRole("listitem", { name: "Evidence metric:service:auth" });
    await waitFor(() => expect(card).toHaveFocus());
    expect(within(card).getByText("Cited")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Hide details" })).toBeInTheDocument();
  });

  it("clicking a citation in the workspace opens the Evidence Explorer on that item", async () => {
    mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis(), 201) });
    const { user } = renderApp("/diagnosis/UC4-0001");
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    const report = await screen.findByRole("region", { name: "Report" });
    await user.click(within(report).getAllByRole("link", { name: "request:c-4261adc1ef" })[0]);
    expect(await screen.findByRole("heading", { level: 1, name: "Evidence Explorer" })).toBeInTheDocument();
    const card = screen.getByRole("listitem", { name: "Evidence request:c-4261adc1ef" });
    await waitFor(() => expect(card).toHaveFocus());
  });

  it("warns about evidence ids that are cited but missing, without inventing them", async () => {
    const d = recommendDiagnosis();
    d.ranked[1].supporting[0].evidence_ids = ["metric:ghost"];
    openEvidence(d);
    expect(await screen.findByText("metric:ghost")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Cited but missing from the evidence list");
    expect(screen.queryByRole("listitem", { name: "Evidence metric:ghost" })).not.toBeInTheDocument();
  });

  it("warns when a focus link points at evidence that is not in the diagnosis", async () => {
    openEvidence(recommendDiagnosis(), "&focus=metric%3Anope");
    expect(await screen.findByRole("note")).toHaveTextContent("Evidence metric:nope is not in this diagnosis.");
  });

  it("shows missing-kind evidence on a CLARIFY diagnosis", async () => {
    openEvidence(clarifyDiagnosis());
    const card = await screen.findByRole("listitem", { name: "Evidence missing:dependency-metrics" });
    expect(within(card).getByText("Missing")).toBeInTheDocument();
    expect(screen.getByLabelText("Group evidence by cause")).toBeDisabled();
  });

  it("renders unknown future evidence kinds", async () => {
    openEvidence(recommendDiagnosis({ evidence: [
      { id: "doc:runbook#2", kind: "doc", text: "Gateway timeout is 10000 ms.", data: {} },
      { id: "trace:span-9", kind: "trace", text: "A brand-new kind", data: {} },
    ] }));
    expect(await screen.findByRole("listitem", { name: "Evidence trace:span-9" })).toHaveTextContent("trace");
    expect(screen.getByRole("listitem", { name: "Evidence doc:runbook#2" })).toHaveTextContent("Doc");
  });

  it("handles an empty evidence list", async () => {
    openEvidence(recommendDiagnosis({ evidence: [] }));
    expect(await screen.findByText("No evidence")).toBeInTheDocument();
  });

  it("asks for a diagnosis when none is selected", async () => {
    mockBackend();
    renderApp("/evidence");
    expect(screen.getByRole("heading", { name: "Choose a diagnosis" })).toBeInTheDocument();
    expect(screen.getByText("No diagnoses in this session")).toBeInTheDocument();
  });
});

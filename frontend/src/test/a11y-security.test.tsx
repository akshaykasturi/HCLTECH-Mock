import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { mockBackend, ok, renderApp } from "./utils";
import { clarifyDiagnosis, recommendDiagnosis } from "./fixtures";

/** Every id referenced by aria-labelledby/-describedby/-controls exists, and no id contains whitespace. */
function checkIdReferences() {
  const ids = [...document.querySelectorAll("[id]")].map((el) => el.id);
  expect(ids.filter((id) => /\s/.test(id))).toEqual([]);
  for (const attr of ["aria-labelledby", "aria-describedby"]) {
    for (const el of document.querySelectorAll(`[${attr}]`)) {
      for (const ref of (el.getAttribute(attr) ?? "").split(/\s+/).filter(Boolean)) {
        expect(document.getElementById(ref), `${attr}="${ref}"`).not.toBeNull();
      }
    }
  }
}

function checkFormLabels() {
  for (const field of document.querySelectorAll("input:not([type=radio]), select, textarea")) {
    const id = field.getAttribute("id");
    const labelled = (id && document.querySelector(`label[for="${id}"]`)) || field.getAttribute("aria-label") || field.closest("label");
    expect(labelled, `field ${id} has no label`).toBeTruthy();
  }
}

describe("accessibility", () => {
  it.each(["/", "/cases", "/diagnosis", "/evidence", "/review", "/audit", "/system-health"])(
    "%s: form fields are labelled and aria references resolve", async (path) => {
      mockBackend();
      renderApp(path);
      await screen.findByRole("heading", { level: 1 });
      await waitFor(() => expect(screen.queryByText("Checking backend…")).not.toBeInTheDocument());
      checkFormLabels();
      checkIdReferences();
    });

  it("a full diagnosis view has valid aria references (regression: ids with spaces)", async () => {
    mockBackend({ "POST /api/diagnose": ok(recommendDiagnosis(), 201) });
    const { user } = renderApp("/diagnosis/UC4-0001");
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    await screen.findByRole("region", { name: "Ranked causes" });
    for (const region of ["Report", "Report checks", "Missing information", "Diagnosis details"]) {
      expect(screen.getByRole("region", { name: region })).toBeInTheDocument();
    }
    checkIdReferences();
  });

  it("supports keyboard navigation: skip link, then the sidebar links", async () => {
    mockBackend();
    const { user } = renderApp("/");
    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveFocus();
    await user.tab(); // logo
    await user.tab();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveFocus();
    await user.tab();
    expect(within(nav).getByRole("link", { name: "Case Explorer" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { level: 1, name: "Case Explorer" })).toBeInTheDocument();
  });

  it("interactive controls have visible focus styles", async () => {
    mockBackend();
    renderApp("/cases");
    await screen.findByText("23 of 23 cases");
    for (const el of [screen.getByRole("button", { name: "Refresh" }), screen.getByRole("link", { name: "Diagnose UC4-0001" }),
                      screen.getByRole("button", { name: "Preview UC4-0001" })]) {
      expect(el.className).toMatch(/focus-visible:outline/);
    }
  });

  it("disables actions that cannot run", async () => {
    mockBackend();
    renderApp("/diagnosis/bad%20id");
    expect(await screen.findByRole("button", { name: "Run diagnosis" })).toBeDisabled();
    expect(screen.getByText("This is not a valid case ID.")).toBeInTheDocument();
  });

  it("announces errors with role=alert and loading with role=status", async () => {
    mockBackend({ "GET /api/cases": "network" });
    renderApp("/cases");
    expect(screen.getByText("Loading cases").closest("[role=status]")).not.toBeNull();
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unreachable");
  });
});

describe("security", () => {
  it("renders backend text as text, never as HTML", async () => {
    const payload = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>';
    const d = recommendDiagnosis({
      evidence: [{ id: "request:c-x", kind: "request", text: payload, data: { html: payload } }],
    });
    d.report!.summary = payload;
    mockBackend({ "POST /api/diagnose": ok(d, 201), [`GET /api/diagnoses/${d.diagnosis_id}`]: ok(d) });
    const { user } = renderApp("/diagnosis/UC4-0001");
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    expect(await screen.findByText(payload)).toBeInTheDocument(); // the literal characters are shown
    expect(document.querySelector("main img")).toBeNull();
    expect(document.querySelector("main script")).toBeNull();
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it("does not store diagnoses, evidence or feedback in browser storage", async () => {
    const local = vi.spyOn(Storage.prototype, "setItem");
    mockBackend({
      "POST /api/diagnose": ok(recommendDiagnosis(), 201),
      "GET /api/diagnoses/dx-recommend-1/feedback": ok([]),
      "POST /api/diagnoses/dx-recommend-1/feedback": ok({ feedback_id: "f1", diagnosis_id: "dx-recommend-1", case_id: "UC4-0001",
        verdict: "confirm", cause_id: null, note: null, created_at: "2026-11-16T10:00:00Z", request_id: null }, 201),
    });
    const { user } = renderApp("/diagnosis/UC4-0001");
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    await user.click(await screen.findByRole("link", { name: "Review this diagnosis" }));
    await user.click(await screen.findByRole("radio", { name: /Confirm/ }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    await screen.findByText(/Feedback saved/);
    expect(local).not.toHaveBeenCalled();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });

  it("shows no diagnosis unless the backend returned one", async () => {
    mockBackend(); // POST /api/diagnose is not mocked: the backend answers 404 NOT_FOUND
    const { user } = renderApp("/diagnosis/UC4-0001");
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    await screen.findByRole("alert");
    expect(screen.queryByText("RECOMMEND")).not.toBeInTheDocument();
    expect(screen.queryByText("CLARIFY")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Ranked causes" })).not.toBeInTheDocument();
  });

  it("a CLARIFY diagnosis shows no invented causes or report", async () => {
    mockBackend({ "POST /api/diagnose": ok(clarifyDiagnosis(), 201) });
    const { user } = renderApp("/diagnosis/UC4-0085");
    await user.click(await screen.findByRole("button", { name: "Run diagnosis" }));
    await screen.findByRole("heading", { name: "More information needed" });
    expect(screen.queryByText(/Most likely cause/)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("listitem").filter((li) => li.getAttribute("aria-label")?.startsWith("Rank"))).toHaveLength(0);
  });

  it("application code never imports test data, writes storage or renders raw HTML", () => {
    const sources = import.meta.glob(["../**/*.{ts,tsx}", "!../test/**", "!../**/*.test.{ts,tsx}"],
                                     { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const files = Object.keys(sources);
    expect(files.length).toBeGreaterThan(20);
    for (const [file, text] of Object.entries(sources)) {
      expect(text, file).not.toMatch(/test\/fixtures|localStorage|sessionStorage|dangerouslySetInnerHTML|innerHTML\s*=/);
      expect(text, file).not.toMatch(/expected_cause|expected_class|expected_outcome/);
    }
  });
});

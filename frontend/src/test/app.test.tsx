import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { fail, mockBackend, ok, renderApp } from "./utils";
import { CASES, HEALTH_NOT_READY, HEALTH_OK } from "./fixtures";

describe("application shell", () => {
  it("renders the dashboard with the sidebar", async () => {
    mockBackend();
    renderApp("/");
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    for (const label of ["Dashboard", "Case Explorer", "Diagnosis", "Evidence Explorer", "Human Review", "Audit History", "System Health"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    await screen.findByTestId("total-cases");
  });

  it("navigates with the sidebar and marks the active page", async () => {
    mockBackend();
    const { user } = renderApp("/");
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    await user.click(within(nav).getByRole("link", { name: "Case Explorer" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Case Explorer" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Case Explorer" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("Case Explorer")).toHaveAttribute("aria-current", "page");
  });

  it("every navigation item opens its page", async () => {
    mockBackend();
    const { user } = renderApp("/");
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    const expected: [string, string][] = [["Case Explorer", "Case Explorer"], ["Diagnosis", "Diagnosis workspace"],
      ["Evidence Explorer", "Evidence Explorer"], ["Human Review", "Human Review"], ["Audit History", "Audit History"],
      ["System Health", "System Health"], ["Dashboard", "Dashboard"]];
    for (const [link, heading] of expected) {
      await user.click(within(nav).getByRole("link", { name: link }));
      expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    }
  });

  it("shows a not-found page for unknown routes", async () => {
    mockBackend();
    const { user } = renderApp("/no/such/page");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Go to the dashboard" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });

  it("opens and closes the mobile navigation", async () => {
    mockBackend();
    const { user } = renderApp("/");
    const open = screen.getByRole("button", { name: "Open navigation" });
    await user.click(open);
    const dialog = screen.getByRole("dialog", { name: "Navigation" });
    expect(within(dialog).getByRole("link", { name: "Dashboard" })).toHaveFocus(); // first nav item, not the logo
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(open).toHaveFocus();
    await user.click(open);
    await user.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Audit History" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Audit History" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("moves focus to the content after navigation and has a skip link", async () => {
    mockBackend();
    const { user } = renderApp("/");
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    await user.click(within(screen.getByRole("navigation", { name: "Main navigation" })).getByRole("link", { name: "Audit History" }));
    await waitFor(() => expect(document.getElementById("main")).toHaveFocus());
  });

  it("shows the backend status in the header", async () => {
    mockBackend({ "GET /health": ok(HEALTH_NOT_READY) });
    renderApp("/audit");
    expect(await screen.findByRole("link", { name: /Backend status: API healthy, pipeline not ready/ })).toBeInTheDocument();
  });
});

describe("dashboard", () => {
  it("shows the case count and health from the API", async () => {
    mockBackend();
    renderApp("/");
    expect(await screen.findByTestId("total-cases")).toHaveTextContent(String(CASES.length));
    expect(await screen.findAllByText("Healthy")).toHaveLength(2); // API + database
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
    expect(screen.getByText(CASES[0].summary)).toBeInTheDocument();
  });

  it("shows loading skeletons while data loads", async () => {
    mockBackend({ "GET /api/cases": { ...ok(CASES) as object, delayMs: 100 } });
    renderApp("/");
    expect(screen.getByText("Loading cases").closest("[role=status]")).not.toBeNull(); // announced skeleton
    expect(await screen.findByTestId("total-cases")).toHaveTextContent("23");
  });

  it("shows pipeline not ready with the backend's detail", async () => {
    mockBackend({ "GET /health": ok(HEALTH_NOT_READY) });
    renderApp("/");
    expect(await screen.findByText("pipeline cannot be imported (ImportError)")).toBeInTheDocument();
    expect(screen.getAllByText("Not ready").length).toBeGreaterThan(0);
  });

  it("refresh reloads cases and health", async () => {
    const backend = mockBackend();
    const { user } = renderApp("/");
    await screen.findByTestId("total-cases");
    const before = backend.callsTo("GET", "/api/cases").length;
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(backend.callsTo("GET", "/api/cases").length).toBe(before + 1));
    expect(backend.callsTo("GET", "/health").length).toBeGreaterThanOrEqual(2);
  });

  it("shows an error with retry when cases fail, and recovers", async () => {
    let failNext = true;
    mockBackend({ "GET /api/cases": () => (failNext ? fail(503, "CASES_UNAVAILABLE", "Case data could not be loaded.") : ok(CASES)) });
    const { user } = renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Cases unavailable");
    failNext = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("total-cases")).toHaveTextContent("23");
  });

  it("does not invent numbers when the backend is down", async () => {
    mockBackend({ "GET /api/cases": "network", "GET /health": "network" });
    renderApp("/");
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Backend unreachable");
    expect(screen.queryByTestId("total-cases")).not.toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });
});

describe("system health", () => {
  it("shows healthy API, database, pipeline and readiness", async () => {
    mockBackend();
    renderApp("/system-health");
    const api = await screen.findByRole("article", { name: "API" });
    await waitFor(() => expect(within(api).getByText("Healthy")).toBeInTheDocument());
    expect(within(screen.getByRole("article", { name: "Audit database" })).getByText("Healthy")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Diagnosis pipeline" })).getByText("Healthy")).toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole("article", { name: "Readiness" })).getByText("Healthy")).toBeInTheDocument());
    expect(screen.getByText(/Last successful check: \d/)).toBeInTheDocument();
  });

  it("never shows the pipeline as healthy when the backend says not_ready", async () => {
    mockBackend({ "GET /health": ok(HEALTH_NOT_READY) });
    renderApp("/system-health");
    const tile = await screen.findByRole("article", { name: "Diagnosis pipeline" });
    await waitFor(() => expect(within(tile).getByText("Not ready")).toBeInTheDocument());
    expect(within(tile).queryByText("Healthy")).not.toBeInTheDocument();
    expect(within(tile).getByText("pipeline cannot be imported (ImportError)")).toBeInTheDocument();
  });

  it("shows database down and readiness not ready", async () => {
    const down = { ...HEALTH_OK, database: "down" };
    mockBackend({ "GET /health": ok(down), "GET /health/ready": fail(503, "DATABASE_UNAVAILABLE", "x") });
    renderApp("/system-health");
    await waitFor(() => expect(within(screen.getByRole("article", { name: "Audit database" })).getByText("Unavailable")).toBeInTheDocument());
    await waitFor(() => expect(within(screen.getByRole("article", { name: "Readiness" })).getByText("Not ready")).toBeInTheDocument());
  });

  it("shows unavailable / unknown on network failure, then refresh recovers", async () => {
    let down = true;
    const backend = mockBackend({ "GET /health": () => (down ? "network" : ok(HEALTH_OK)) });
    const { user } = renderApp("/system-health");
    await waitFor(() => expect(within(screen.getByRole("article", { name: "API" })).getByText("Unavailable")).toBeInTheDocument());
    expect(within(screen.getByRole("article", { name: "Audit database" })).getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByText("Last successful check: never")).toBeInTheDocument();
    down = false;
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(within(screen.getByRole("article", { name: "API" })).getByText("Healthy")).toBeInTheDocument());
    expect(backend.callsTo("GET", "/health").length).toBeGreaterThanOrEqual(2);
  });
});

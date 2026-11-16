import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { fail, mockBackend, ok, renderApp } from "./utils";
import { CASES } from "./fixtures";

const rows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1); // skip header
const firstCellIds = () => rows().map((r) => within(r).getAllByRole("cell")[0].textContent);

describe("case explorer", () => {
  it("lists cases from the API with pagination", async () => {
    mockBackend();
    const { user } = renderApp("/cases");
    await screen.findByText(`${CASES.length} of ${CASES.length} cases`);
    expect(rows()).toHaveLength(15);
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(rows()).toHaveLength(8);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("searches by id, route and summary (debounced)", async () => {
    mockBackend();
    const { user } = renderApp("/cases");
    await screen.findByText("23 of 23 cases");
    const search = screen.getByLabelText("Search cases by ID, route or summary");
    await user.type(search, "UC4-0007");
    await waitFor(() => expect(firstCellIds()).toEqual(["UC4-0007"]));
    await user.clear(search);
    await user.type(search, "payments");
    await waitFor(() => expect(screen.getByText("7 of 23 cases")).toBeInTheDocument());
    await user.clear(search);
    await user.type(search, "HTTP 504");
    await waitFor(() => expect(screen.getByText("8 of 23 cases")).toBeInTheDocument());
  });

  it("filters by route and split", async () => {
    mockBackend();
    const { user } = renderApp("/cases");
    await screen.findByText("23 of 23 cases");
    await user.selectOptions(screen.getByLabelText("Filter by route"), "GET /v1/search");
    await waitFor(() => expect(screen.getByText("8 of 23 cases")).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Filter by split"), "test");
    await waitFor(() => expect(screen.getByText("2 of 23 cases")).toBeInTheDocument()); // UC4-0001 and UC4-0013
    expect(firstCellIds()).toEqual(["UC4-0001", "UC4-0013"]);
    await user.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(screen.getByText("23 of 23 cases")).toBeInTheDocument());
  });

  it("sorts by column and reports the sort to assistive tech", async () => {
    mockBackend();
    const { user } = renderApp("/cases");
    await screen.findByText("23 of 23 cases");
    const idHeader = screen.getByRole("columnheader", { name: /Case/ });
    expect(idHeader).toHaveAttribute("aria-sort", "ascending");
    expect(firstCellIds()[0]).toBe("UC4-0001");
    await user.click(within(idHeader).getByRole("button"));
    expect(idHeader).toHaveAttribute("aria-sort", "descending");
    expect(firstCellIds()[0]).toBe("UC4-0023");
    const routeHeader = screen.getByRole("columnheader", { name: /Route/ });
    await user.click(within(routeHeader).getByRole("button"));
    expect(routeHeader).toHaveAttribute("aria-sort", "ascending");
    expect(within(rows()[0]).getAllByRole("cell")[1]).toHaveTextContent("GET /v1/orders/{id}");
  });

  it("selects a case for preview and opens its diagnosis workspace", async () => {
    mockBackend();
    const { user } = renderApp("/cases");
    await screen.findByText("23 of 23 cases");
    expect(screen.getByText("No case selected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Preview UC4-0002" }));
    const preview = screen.getByRole("region", { name: "Case preview" });
    expect(within(preview).getByText("UC4-0002")).toBeInTheDocument();
    expect(within(preview).getByText(CASES[1].summary)).toBeInTheDocument();
    await user.click(within(preview).getByRole("button", { name: "Open diagnosis workspace" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Diagnosis workspace · UC4-0002" })).toBeInTheDocument();
  });

  it("the row Diagnose link opens the workspace", async () => {
    mockBackend();
    const { user } = renderApp("/cases");
    await user.click(await screen.findByRole("link", { name: "Diagnose UC4-0003" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Diagnosis workspace · UC4-0003" })).toBeInTheDocument();
  });

  it("handles an empty case list", async () => {
    mockBackend({ "GET /api/cases": ok([]) });
    renderApp("/cases");
    expect(await screen.findByText("No cases")).toBeInTheDocument();
  });

  it("shows a no-match state with a clear action", async () => {
    mockBackend();
    const { user } = renderApp("/cases");
    await screen.findByText("23 of 23 cases");
    await user.type(screen.getByLabelText("Search cases by ID, route or summary"), "zzz-nothing");
    expect(await screen.findByText("No cases match your filters")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(screen.getByText("23 of 23 cases")).toBeInTheDocument());
  });

  it("shows API errors and retries", async () => {
    let attempts = 0;
    mockBackend({ "GET /api/cases": () => (++attempts === 1 ? "network" : ok(CASES)) });
    const { user } = renderApp("/cases");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Backend unreachable");
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("23 of 23 cases")).toBeInTheDocument();
  });

  it("shows a server error message", async () => {
    mockBackend({ "GET /api/cases": fail(500, "INTERNAL_ERROR", "An unexpected error occurred.") });
    renderApp("/cases");
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error");
  });

  it("never displays evaluation labels even if the backend sent them", async () => {
    const leaky = CASES.slice(0, 2).map((c) => ({ ...c, expected_cause: "SECRET_LABEL_token_expired", difficulty: "hard-label" }));
    mockBackend({ "GET /api/cases": ok(leaky) });
    renderApp("/cases");
    await screen.findByText("2 of 2 cases");
    expect(document.body.textContent).not.toContain("SECRET_LABEL");
    expect(document.body.textContent).not.toContain("hard-label");
  });
});

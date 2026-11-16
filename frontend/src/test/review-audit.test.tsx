import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { deferred, fail, mockBackend, ok, renderApp, type Reply } from "./utils";
import { clarifyDiagnosis, recommendDiagnosis } from "./fixtures";
import type { FeedbackRecord } from "../lib/types";

const D = recommendDiagnosis();
const BASE = `/api/diagnoses/${D.diagnosis_id}`;

function record(body: { verdict: string; cause_id?: string; note?: string }, n = 1): FeedbackRecord {
  return { feedback_id: `fb-${n}`, diagnosis_id: D.diagnosis_id, case_id: D.case_id, verdict: body.verdict,
           cause_id: body.cause_id ?? null, note: body.note ?? null, created_at: "2026-11-16T10:05:00Z", request_id: "r-1" };
}

/** Backend with an in-memory, append-only feedback list. */
function reviewBackend(post?: (body: unknown) => Reply | Promise<Reply>) {
  const saved: FeedbackRecord[] = [];
  const backend = mockBackend({
    [`GET ${BASE}`]: ok(D),
    [`GET ${BASE}/feedback`]: () => ok([...saved]),
    [`POST ${BASE}/feedback`]: async ({ body }) => {
      if (post) return post(body);
      const r = record(body as { verdict: string }, saved.length + 1);
      saved.push(r);
      return ok(r, 201);
    },
  });
  return { backend, saved };
}

async function openReview() {
  const view = renderApp(`/review?d=${D.diagnosis_id}`);
  await screen.findByRole("heading", { name: "Add reviewer feedback" });
  await screen.findByText("No feedback yet");
  return view;
}

describe("human review", () => {
  it("confirms the whole diagnosis without cause_id", async () => {
    const { backend } = reviewBackend();
    const { user } = await openReview();
    await user.click(screen.getByRole("radio", { name: /Confirm/ }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    await waitFor(() => expect(backend.callsTo("POST", `${BASE}/feedback`)).toHaveLength(1));
    expect(backend.callsTo("POST", `${BASE}/feedback`)[0].body).toEqual({ verdict: "confirm" });
    expect(await screen.findByText("Feedback saved: confirm on the whole diagnosis.")).toBeInTheDocument();
    const history = await screen.findByRole("list", { name: "Feedback records" });
    expect(within(history).getByText("Whole diagnosis")).toBeInTheDocument();
  });

  it("rejects a specific cause, sending RankedCause.cause (never the rank)", async () => {
    const { backend } = reviewBackend();
    const { user } = await openReview();
    await user.click(screen.getByRole("radio", { name: /Reject/ }));
    await user.selectOptions(screen.getByLabelText("Cause (optional)"), "invalid_api_key");
    await user.type(screen.getByLabelText(/Note/), "Key registry shows the key is valid.");
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    await waitFor(() => expect(backend.callsTo("POST", `${BASE}/feedback`)).toHaveLength(1));
    expect(backend.callsTo("POST", `${BASE}/feedback`)[0].body).toEqual({
      verdict: "reject", cause_id: "invalid_api_key", note: "Key registry shows the key is valid." });
    const history = await screen.findByRole("list", { name: "Feedback records" });
    expect(within(history).getByText("invalid_api_key")).toBeInTheDocument();
    expect(within(history).getByText("Key registry shows the key is valid.")).toBeInTheDocument();
  });

  it("lists causes by rank with their cause names as values", async () => {
    reviewBackend();
    await openReview();
    const options = within(screen.getByLabelText("Cause (optional)")).getAllByRole("option");
    expect(options.map((o) => (o as HTMLOptionElement).value)).toEqual(
      ["", "token_expired", "invalid_api_key", "client_timeout_too_low", "missing_scope", "ip_not_allowlisted", "upstream_dependency_slow"]);
  });

  it("annotate needs a meaningful note and sends nothing until it has one", async () => {
    const { backend } = reviewBackend();
    const { user } = await openReview();
    await user.click(screen.getByRole("radio", { name: /Annotate/ }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(screen.getByText("An annotation needs a note (at least 3 characters).")).toBeInTheDocument();
    expect(screen.getByLabelText(/Note/)).toHaveAttribute("aria-invalid", "true");
    expect(backend.callsTo("POST", `${BASE}/feedback`)).toHaveLength(0);
    await user.type(screen.getByLabelText(/Note/), "Re-check after the next deploy.");
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    await waitFor(() => expect(backend.callsTo("POST", `${BASE}/feedback`)[0]?.body)
      .toEqual({ verdict: "annotate", note: "Re-check after the next deploy." }));
  });

  it("requires a verdict", async () => {
    const { backend } = reviewBackend();
    const { user } = await openReview();
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(screen.getByText("Choose confirm, reject or annotate.")).toBeInTheDocument();
    expect(backend.callsTo("POST", `${BASE}/feedback`)).toHaveLength(0);
  });

  it("shows the backend's UNKNOWN_CAUSE rejection", async () => {
    reviewBackend(() => fail(422, "UNKNOWN_CAUSE", "cause_id is not a cause of this diagnosis."));
    const { user } = await openReview();
    await user.click(screen.getByRole("radio", { name: /Confirm/ }));
    await user.selectOptions(screen.getByLabelText("Cause (optional)"), "token_expired");
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unknown cause");
  });

  it("prevents duplicate submissions while saving", async () => {
    const gate = deferred<Reply>();
    const { backend } = reviewBackend(() => gate.promise);
    const { user } = await openReview();
    await user.click(screen.getByRole("radio", { name: /Confirm/ }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    const busy = screen.getByRole("button", { name: "Saving feedback…" });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(backend.callsTo("POST", `${BASE}/feedback`)).toHaveLength(1);
    gate.resolve(ok(record({ verdict: "confirm" }), 201));
    expect(await screen.findByText(/Feedback saved/)).toBeInTheDocument();
  });

  it("shows a failure and keeps the form", async () => {
    reviewBackend(() => fail(503, "DATABASE_UNAVAILABLE", "The audit database is not available."));
    const { user } = await openReview();
    await user.click(screen.getByRole("radio", { name: /Confirm/ }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Audit database unavailable");
    expect(screen.getByRole("radio", { name: /Confirm/ })).toBeChecked();
  });

  it("shows existing feedback history from the backend", async () => {
    mockBackend({
      [`GET ${BASE}`]: ok(D),
      [`GET ${BASE}/feedback`]: ok([record({ verdict: "reject", cause_id: "token_expired", note: "Token was fresh." }, 1),
                                    record({ verdict: "annotate", note: "Escalated to auth team." }, 2)]),
    });
    renderApp(`/review?d=${D.diagnosis_id}`);
    const history = await screen.findByRole("list", { name: "Feedback records" });
    expect(within(history).getAllByRole("listitem")).toHaveLength(2);
    expect(within(history).getByText("Token was fresh.")).toBeInTheDocument();
  });

  it("on CLARIFY only whole-diagnosis feedback is possible", async () => {
    const c = clarifyDiagnosis();
    mockBackend({ [`GET /api/diagnoses/${c.diagnosis_id}`]: ok(c), [`GET /api/diagnoses/${c.diagnosis_id}/feedback`]: ok([]) });
    renderApp(`/review?d=${c.diagnosis_id}`);
    expect(await screen.findByLabelText("Cause (optional)")).toBeDisabled();
    expect(screen.getByText("This diagnosis claims no cause, so feedback applies to the whole diagnosis.")).toBeInTheDocument();
  });

  it("asks for a diagnosis when there is none", async () => {
    mockBackend();
    const { user } = renderApp("/review");
    expect(screen.getByRole("heading", { name: "Choose a diagnosis to review" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Diagnosis ID"), "bad id!");
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByText(/Enter a diagnosis ID/)).toBeInTheDocument();
  });
});

describe("audit history", () => {
  it("verifies the audit chain", async () => {
    mockBackend({ "GET /api/audit/verify": ok({ valid: true, events_checked: 12, head_hash: "a".repeat(64), first_bad_seq: null, reason: null }) });
    const { user } = renderApp("/audit");
    await user.click(screen.getByRole("button", { name: "Verify chain" }));
    expect(await screen.findByText("Chain verified")).toBeInTheDocument();
    expect(screen.getByText("12 events checked, no gaps or edits found.")).toBeInTheDocument();
  });

  it("reports a broken chain accurately", async () => {
    mockBackend({ "GET /api/audit/verify": ok({ valid: false, events_checked: 4, head_hash: "b".repeat(64), first_bad_seq: 5,
                                                reason: "hash does not match the event's contents" }) });
    const { user } = renderApp("/audit");
    await user.click(screen.getByRole("button", { name: "Verify chain" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Chain check failed");
    expect(alert).toHaveTextContent("At event #5: hash does not match the event's contents");
    expect(screen.queryByText("Chain verified")).not.toBeInTheDocument();
  });

  it("shows a verification error", async () => {
    mockBackend({ "GET /api/audit/verify": fail(503, "DATABASE_UNAVAILABLE", "x") });
    const { user } = renderApp("/audit");
    await user.click(screen.getByRole("button", { name: "Verify chain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Audit database unavailable");
  });

  it("looks up a diagnosis and its feedback, then opens it", async () => {
    mockBackend({ [`GET ${BASE}`]: ok(D), [`GET ${BASE}/feedback`]: ok([record({ verdict: "confirm" })]) });
    const { user } = renderApp("/audit");
    await user.type(screen.getByLabelText("Diagnosis ID"), D.diagnosis_id);
    await user.click(screen.getByRole("button", { name: "Look up" }));
    expect(await screen.findByText("1 record")).toBeInTheDocument();
    expect(screen.getByText("Token expired")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Open diagnosis" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Diagnosis · UC4-0001" })).toBeInTheDocument();
  });

  it("reports a missing diagnosis and validates the id", async () => {
    mockBackend({ "GET /api/diagnoses/dx-missing": fail(404, "DIAGNOSIS_NOT_FOUND", "x") });
    const { user } = renderApp("/audit");
    await user.click(screen.getByRole("button", { name: "Look up" }));
    expect(screen.getByText(/Enter a diagnosis ID/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Diagnosis ID"), "dx-missing");
    await user.click(screen.getByRole("button", { name: "Look up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Diagnosis not found");
  });

  it("shows the timeline as integration pending and never calls an invented endpoint", async () => {
    const backend = mockBackend();
    renderApp("/audit");
    expect(screen.getByText("Integration pending")).toBeInTheDocument();
    expect(screen.getByText(/does not have an endpoint that lists audit events/)).toBeInTheDocument();
    await waitFor(() => expect(backend.calls.length).toBeGreaterThan(0));
    const paths = backend.calls.map((c) => c.path);
    expect(paths.every((p) => ["/health", "/health/ready", "/api/cases", "/api/audit/verify"].includes(p))).toBe(true);
  });
});

import { describe, expect, it, vi } from "vitest";
import { ApiError, PIPELINE_NOT_READY_MESSAGE, assertDiagnosis, createApiClient, describeError, makeEndpoints } from "./api";
import { recommendDiagnosis } from "../test/fixtures";

function fetchReturning(status: number, body: string | object, headers: Record<string, string> = {}) {
  return vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () => new Response(typeof body === "string" ? body : JSON.stringify(body),
                                         { status, headers: { "Content-Type": "application/json", ...headers } }));
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (e) {
    expect(e).toBeInstanceOf(ApiError);
    return e as ApiError;
  }
  throw new Error("expected the request to fail");
}

describe("API client", () => {
  it("returns data from a successful envelope", async () => {
    const fetchImpl = fetchReturning(200, { ok: true, data: [1, 2], error: null });
    const client = createApiClient({ baseUrl: "", fetchImpl });
    await expect(client.request("/api/cases")).resolves.toEqual([1, 2]);
  });

  it("uses the configured base URL and strips trailing slashes", async () => {
    const fetchImpl = fetchReturning(200, { ok: true, data: null, error: null });
    await createApiClient({ baseUrl: "http://127.0.0.1:8000/", fetchImpl }).request("/health");
    expect(fetchImpl).toHaveBeenCalledWith("http://127.0.0.1:8000/health", expect.objectContaining({ method: "GET" }));
  });

  it("sends JSON bodies for POST", async () => {
    const fetchImpl = fetchReturning(201, { ok: true, data: {}, error: null });
    await createApiClient({ baseUrl: "", fetchImpl }).request("/api/diagnose", { method: "POST", body: { case_id: "UC4-0001" } });
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.body).toBe('{"case_id":"UC4-0001"}');
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("turns an error envelope into ApiError with code, status and request id", async () => {
    const fetchImpl = fetchReturning(503, { ok: false, data: null, error: { code: "DIAGNOSIS_NOT_READY", message: "not ready" } },
                                     { "X-Request-ID": "req-123" });
    const err = await caught(createApiClient({ baseUrl: "", fetchImpl }).request("/api/diagnose"));
    expect(err).toMatchObject({ kind: "http", status: 503, code: "DIAGNOSIS_NOT_READY", requestId: "req-123" });
    expect(describeError(err).message).toBe(PIPELINE_NOT_READY_MESSAGE);
  });

  it.each([
    [404, "CASE_NOT_FOUND", "Case not found"],
    [422, "VALIDATION_ERROR", "Invalid request"],
    [500, "INTERNAL_ERROR", "Server error"],
    [502, "DIAGNOSIS_FAILED", "Diagnosis failed"],
    [502, "DIAGNOSIS_INVALID", "Diagnosis rejected"],
    [503, "DATABASE_UNAVAILABLE", "Audit database unavailable"],
    [504, "DIAGNOSIS_TIMEOUT", "Diagnosis timed out"],
  ])("maps HTTP %i %s to a clear message", async (status, code, title) => {
    const fetchImpl = fetchReturning(status, { ok: false, data: null, error: { code, message: "server text" } });
    const err = await caught(createApiClient({ baseUrl: "", fetchImpl }).request("/x"));
    expect(err.status).toBe(status);
    expect(describeError(err).title).toBe(title);
  });

  it("handles an HTTP error without an envelope", async () => {
    const err = await caught(createApiClient({ baseUrl: "", fetchImpl: fetchReturning(500, "<html>oops</html>") }).request("/x"));
    expect(err).toMatchObject({ kind: "http", status: 500, code: "HTTP_500" });
  });

  it("rejects invalid JSON on success", async () => {
    const err = await caught(createApiClient({ baseUrl: "", fetchImpl: fetchReturning(200, "{not json") }).request("/x"));
    expect(err).toMatchObject({ kind: "invalid_response", code: "INVALID_JSON" });
  });

  it("rejects a 200 response that is not an envelope", async () => {
    const err = await caught(createApiClient({ baseUrl: "", fetchImpl: fetchReturning(200, { cases: [] }) }).request("/x"));
    expect(err.code).toBe("INVALID_ENVELOPE");
  });

  it("reports network failures", async () => {
    const fetchImpl = vi.fn(async () => { throw new TypeError("Failed to fetch"); });
    const err = await caught(createApiClient({ baseUrl: "", fetchImpl }).request("/x"));
    expect(err.kind).toBe("network");
    expect(describeError(err).title).toBe("Backend unreachable");
  });

  function hangingFetch() {
    return vi.fn((_url: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
  }

  it("times out", async () => {
    const err = await caught(createApiClient({ baseUrl: "", fetchImpl: hangingFetch(), timeoutMs: 20 }).request("/x"));
    expect(err).toMatchObject({ kind: "timeout", code: "TIMEOUT" });
  });

  it("can be cancelled with an AbortSignal", async () => {
    const ctl = new AbortController();
    const pending = createApiClient({ baseUrl: "", fetchImpl: hangingFetch() }).request("/x", { signal: ctl.signal });
    ctl.abort();
    expect((await caught(pending)).kind).toBe("aborted");
  });

  it("diagnose posts the case id and validates the result", async () => {
    const fetchImpl = fetchReturning(201, { ok: true, data: recommendDiagnosis(), error: null });
    const d = await makeEndpoints(createApiClient({ baseUrl: "", fetchImpl })).diagnose("UC4-0001");
    expect(d.outcome).toBe("RECOMMEND");
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/diagnose");
    expect(JSON.parse(init.body as string)).toEqual({ case_id: "UC4-0001" });
  });

  it("rejects a diagnosis with an ESCALATE outcome or missing fields", () => {
    expect(() => assertDiagnosis({ ...recommendDiagnosis(), outcome: "ESCALATE" })).toThrow(ApiError);
    expect(() => assertDiagnosis({ diagnosis_id: "x" })).toThrow(ApiError);
  });

  it("encodes ids in paths", async () => {
    const fetchImpl = fetchReturning(200, { ok: true, data: [], error: null });
    await makeEndpoints(createApiClient({ baseUrl: "", fetchImpl })).feedback("a/b");
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/diagnoses/a%2Fb/feedback");
  });
});

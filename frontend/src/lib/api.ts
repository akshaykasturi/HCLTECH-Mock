// One HTTP client for the FastAPI backend. Every response is the {ok, data, error} envelope.
// Errors are normalised into ApiError so screens can show one consistent message and retry.
import type {
  CaseSummary, ChainStatus, Diagnosis, Envelope, FeedbackRecord, FeedbackRequest, HealthData,
} from "./types";

export type ApiErrorKind = "http" | "network" | "timeout" | "aborted" | "invalid_response";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly requestId: string | null;

  constructor(kind: ApiErrorKind, code: string, message: string, status: number | null = null,
              requestId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

export const DEFAULT_TIMEOUT_MS = 15_000;
/** The backend allows the pipeline 60 s by default; give it a little more before giving up. */
export const DIAGNOSE_TIMEOUT_MS = 75_000;

export interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface ApiClientConfig {
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

/** Base URL from VITE_API_BASE_URL; empty means same origin (the Vite dev proxy in development). */
export function configuredBaseUrl(): string {
  const raw = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
  return raw.trim().replace(/\/+$/, "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isEnvelope(value: unknown): value is Envelope<unknown> {
  return isRecord(value) && typeof value.ok === "boolean" && "data" in value && "error" in value;
}

export function createApiClient(config: ApiClientConfig = {}) {
  const baseUrl = (config.baseUrl ?? configuredBaseUrl()).replace(/\/+$/, "");
  const defaultTimeout = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const doFetch = (...args: Parameters<typeof fetch>) => (config.fetchImpl ?? globalThis.fetch)(...args);

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs ?? defaultTimeout);
    const onOuterAbort = () => controller.abort();
    if (options.signal) {
      if (options.signal.aborted) controller.abort();
      else options.signal.addEventListener("abort", onOuterAbort, { once: true });
    }

    let response: Response;
    try {
      response = await doFetch(`${baseUrl}${path}`, {
        method: options.method ?? "GET",
        headers: options.body !== undefined
          ? { "Content-Type": "application/json", Accept: "application/json" }
          : { Accept: "application/json" },
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
    } catch {
      if (timedOut) throw new ApiError("timeout", "TIMEOUT", "The request timed out.");
      if (controller.signal.aborted) throw new ApiError("aborted", "ABORTED", "The request was cancelled.");
      throw new ApiError("network", "NETWORK_ERROR", "Cannot reach the diagnostics backend.");
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", onOuterAbort);
    }

    const requestId = response.headers.get("X-Request-ID");
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      if (!response.ok) {
        throw new ApiError("http", `HTTP_${response.status}`, `The server answered HTTP ${response.status}.`,
                           response.status, requestId);
      }
      throw new ApiError("invalid_response", "INVALID_JSON", "The server sent a response that is not valid JSON.",
                         response.status, requestId);
    }

    if (!isEnvelope(body)) {
      if (!response.ok) {
        throw new ApiError("http", `HTTP_${response.status}`, `The server answered HTTP ${response.status}.`,
                           response.status, requestId);
      }
      throw new ApiError("invalid_response", "INVALID_ENVELOPE", "The server response has an unexpected shape.",
                         response.status, requestId);
    }
    if (!body.ok || !response.ok) {
      const code = body.error?.code ?? `HTTP_${response.status}`;
      const message = body.error?.message ?? `The server answered HTTP ${response.status}.`;
      throw new ApiError("http", code, message, response.status, requestId);
    }
    return body.data as T;
  }

  return { request, baseUrl };
}

export type ApiClient = ReturnType<typeof createApiClient>;

// ---------- response checks (light, so a changed backend fails loudly instead of rendering garbage) ----------

function invalid(what: string): never {
  throw new ApiError("invalid_response", "INVALID_RESPONSE", `The server sent an unexpected ${what}.`);
}

export function assertCases(data: unknown): CaseSummary[] {
  if (!Array.isArray(data)) invalid("case list");
  for (const c of data) {
    if (!isRecord(c) || typeof c.id !== "string" || typeof c.route !== "string" || typeof c.summary !== "string") {
      invalid("case list");
    }
  }
  return data as CaseSummary[];
}

export function assertHealth(data: unknown): HealthData {
  if (!isRecord(data) || typeof data.api !== "string" || typeof data.database !== "string"
      || typeof data.pipeline !== "string") invalid("health status");
  return data as unknown as HealthData;
}

export function assertDiagnosis(data: unknown): Diagnosis {
  if (!isRecord(data) || typeof data.diagnosis_id !== "string" || typeof data.case_id !== "string"
      || (data.outcome !== "RECOMMEND" && data.outcome !== "CLARIFY") || typeof data.escalate !== "boolean"
      || !Array.isArray(data.ranked) || !Array.isArray(data.evidence) || !Array.isArray(data.missing_info)) {
    invalid("diagnosis");
  }
  const d = data as Record<string, unknown>;
  return {
    alternatives: [], tell_apart: null, report: null, report_findings: [], groundedness: null,
    generator: "template", trace: [], ...d,
  } as unknown as Diagnosis;
}

export function assertFeedbackList(data: unknown): FeedbackRecord[] {
  if (!Array.isArray(data)) invalid("feedback list");
  return data as FeedbackRecord[];
}

export function assertChain(data: unknown): ChainStatus {
  if (!isRecord(data) || typeof data.valid !== "boolean") invalid("audit chain status");
  return data as unknown as ChainStatus;
}

// ---------- endpoints (the only ones the backend implements) ----------

export const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;

export function makeEndpoints(client: ApiClient, options: { diagnoseTimeoutMs?: number } = {}) {
  const id = (value: string) => encodeURIComponent(value);
  const diagnoseTimeout = options.diagnoseTimeoutMs ?? DIAGNOSE_TIMEOUT_MS;
  return {
    health: (signal?: AbortSignal) => client.request<unknown>("/health", { signal }).then(assertHealth),
    ready: (signal?: AbortSignal) => client.request<unknown>("/health/ready", { signal }).then(assertHealth),
    cases: (signal?: AbortSignal) => client.request<unknown>("/api/cases", { signal }).then(assertCases),
    diagnose: (caseId: string, signal?: AbortSignal) =>
      client.request<unknown>("/api/diagnose", {
        method: "POST", body: { case_id: caseId }, signal, timeoutMs: diagnoseTimeout,
      }).then(assertDiagnosis),
    diagnosis: (diagnosisId: string, signal?: AbortSignal) =>
      client.request<unknown>(`/api/diagnoses/${id(diagnosisId)}`, { signal }).then(assertDiagnosis),
    feedback: (diagnosisId: string, signal?: AbortSignal) =>
      client.request<unknown>(`/api/diagnoses/${id(diagnosisId)}/feedback`, { signal }).then(assertFeedbackList),
    addFeedback: (diagnosisId: string, body: FeedbackRequest, signal?: AbortSignal) =>
      client.request<FeedbackRecord>(`/api/diagnoses/${id(diagnosisId)}/feedback`, { method: "POST", body, signal }),
    verifyAudit: (signal?: AbortSignal) =>
      client.request<unknown>("/api/audit/verify", { signal }).then(assertChain),
  };
}

export type Endpoints = ReturnType<typeof makeEndpoints>;

// ---------- user-facing messages ----------

export interface ErrorDescription {
  title: string;
  message: string;
  retryable: boolean;
}

export const PIPELINE_NOT_READY_MESSAGE =
  "AI diagnosis is not available yet. The diagnosis pipeline is still being integrated.";

export function describeError(error: unknown): ErrorDescription {
  if (!(error instanceof ApiError)) {
    return { title: "Something went wrong", message: "An unexpected error occurred.", retryable: true };
  }
  switch (error.kind) {
    case "network":
      return { title: "Backend unreachable",
               message: "Cannot reach the diagnostics backend. Check that the FastAPI server is running.",
               retryable: true };
    case "timeout":
      return { title: "Request timed out", message: "The server took too long to answer.", retryable: true };
    case "aborted":
      return { title: "Request cancelled", message: "The request was cancelled.", retryable: true };
    case "invalid_response":
      return { title: "Unexpected response", message: error.message, retryable: true };
  }
  switch (error.code) {
    case "DIAGNOSIS_NOT_READY":
      return { title: "Diagnosis pipeline not ready", message: PIPELINE_NOT_READY_MESSAGE, retryable: true };
    case "CASE_NOT_FOUND":
      return { title: "Case not found", message: "This case does not exist on the backend.", retryable: false };
    case "DIAGNOSIS_NOT_FOUND":
      return { title: "Diagnosis not found", message: "No saved diagnosis has this ID.", retryable: false };
    case "UNKNOWN_CAUSE":
      return { title: "Unknown cause", message: "That cause is not part of this diagnosis.", retryable: false };
    case "DIAGNOSIS_FAILED":
      return { title: "Diagnosis failed", message: "The diagnosis service failed for this case.", retryable: true };
    case "DIAGNOSIS_INVALID":
      return { title: "Diagnosis rejected",
               message: "The diagnosis service returned a result that failed the backend's checks, so nothing was shown or saved.",
               retryable: true };
    case "DIAGNOSIS_TIMEOUT":
      return { title: "Diagnosis timed out", message: "The diagnosis took too long and was not saved.", retryable: true };
    case "DATABASE_UNAVAILABLE":
      return { title: "Audit database unavailable", message: "The audit database is not available.", retryable: true };
    case "CASES_UNAVAILABLE":
      return { title: "Cases unavailable", message: "Case data could not be loaded on the server.", retryable: true };
    case "DIAGNOSIS_CONFLICT":
      return { title: "Already saved", message: "A diagnosis with this ID is already saved.", retryable: false };
  }
  if (error.status === 422) {
    return { title: "Invalid request", message: error.message, retryable: false };
  }
  if (error.status === 404) return { title: "Not found", message: error.message, retryable: false };
  if (error.status !== null && error.status >= 500) {
    return { title: "Server error", message: "The server hit an unexpected error. Try again.", retryable: true };
  }
  return { title: "Request failed", message: error.message, retryable: true };
}

// One place that talks to the backend. Every response uses the envelope {ok, request_id, data, error}.
// Base URL: VITE_API_URL if set. Otherwise production builds call the same origin ("") and
// vercel.json forwards /api/* and /health to the backend, so the browser only ever talks to the
// Vercel domain (no CORS, nothing for ad blockers to block). Dev calls the local backend.
const BASE = (import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://127.0.0.1:8000")).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { code, requestId, retryable } = {}) {
    super(message);
    this.code = code;
    this.requestId = requestId;
    this.retryable = retryable;
  }
}

async function call(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(`Can't reach the server at ${BASE || window.location.origin}. Check that the backend is running.`, {
      code: "NETWORK_ERROR",
      retryable: true,
    });
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(`The server replied with status ${response.status} and no readable body.`, {
      code: "BAD_RESPONSE",
    });
  }
  if (!body.ok) {
    throw new ApiError(body.error?.message || "Request failed.", {
      code: body.error?.code,
      requestId: body.request_id,
      retryable: body.error?.retryable,
    });
  }
  return body.data;
}

export const api = {
  health: () => call("/health"),
  analyze: (ticket) => call("/api/analyze", { method: "POST", body: JSON.stringify(ticket) }),
  listAnalyses: (outcome) => call(`/api/analyses?limit=50${outcome ? `&outcome=${outcome}` : ""}`),
  getAnalysis: (id) => call(`/api/analyses/${id}`),
  sendFeedback: (id, feedback) =>
    call(`/api/analyses/${id}/feedback`, { method: "POST", body: JSON.stringify(feedback) }),
  stats: () => call("/api/stats"),
};

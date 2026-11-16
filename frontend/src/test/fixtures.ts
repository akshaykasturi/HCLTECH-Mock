// TEST DATA ONLY. Shaped like the backend's models.Diagnosis; used by the mocked fetch in tests.
// The application never imports this file.
import type { CaseSummary, Diagnosis, HealthData, RankedCause } from "../lib/types";

export const CASES: CaseSummary[] = Array.from({ length: 23 }, (_, i) => {
  const n = String(i + 1).padStart(4, "0");
  const routes = ["GET /v1/search", "GET /v1/orders/{id}", "POST /v1/payments"];
  const statuses = [401, 504, 429];
  return {
    id: `UC4-${n}`,
    route: routes[i % 3],
    summary: `HTTP ${statuses[i % 3]} on ${routes[i % 3]}, onset 2026-10-${String((i % 28) + 1).padStart(2, "0")} 05:13 UTC`,
    split: i % 4 === 0 ? "test" : i % 4 === 1 ? "calibration" : "train",
  };
});

export const HEALTH_OK: HealthData = { api: "up", database: "up", pipeline: "ready", pipeline_detail: "ready" };
export const HEALTH_NOT_READY: HealthData = {
  api: "up", database: "up", pipeline: "not_ready", pipeline_detail: "pipeline cannot be imported (ImportError)",
};

function cause(rank: number, name: string, confidence: number, extra: Partial<RankedCause> = {}): RankedCause {
  return {
    rank, cause: name, failure_class: "authentication", confidence, status: "unsupported", near_tie: false,
    supporting: [], contradicting: [], confirming_seen: [], confirming_missing: [],
    first_check: `check_${name}`, escalate: false, missing_info: [], ...extra,
  };
}

export function recommendDiagnosis(overrides: Partial<Diagnosis> = {}): Diagnosis {
  return {
    diagnosis_id: "dx-recommend-1",
    created_at: "2026-11-16T10:00:00Z",
    case_id: "UC4-0001",
    route: "GET /v1/search",
    onset_ts: "2026-10-05T00:34:00Z",
    outcome: "RECOMMEND",
    escalate: false,
    failure_class: "authentication",
    class_confidence: 0.997203,
    // Deliberately out of order: the UI must sort by rank.
    ranked: [
      cause(2, "invalid_api_key", 0.0204, {
        supporting: [{ signal: "key_format_bad", present: true, ratio: 1.5, evidence_ids: ["request:c-4261adc1ef"] }],
        contradicting: [{ signal: "key_valid_recently", present: true, ratio: 0.3, evidence_ids: ["traffic:window"] }],
      }),
      cause(1, "token_expired", 0.9769, {
        status: "likely",
        supporting: [{ signal: "token_age_over_ttl", present: true, ratio: 4.0, evidence_ids: ["request:c-4261adc1ef"] }],
        contradicting: [{ signal: "clock_skew", present: false, ratio: 0.8, evidence_ids: ["metric:service:auth"] }],
        first_check: "check_token_expiry",
      }),
      cause(3, "client_timeout_too_low", 0.0014),
      cause(4, "missing_scope", 0.0003),
      cause(5, "ip_not_allowlisted", 0.0002),
      cause(6, "upstream_dependency_slow", 0.0001, { status: "probable" }),
    ],
    alternatives: [],
    tell_apart: null,
    evidence: [
      { id: "request:c-4261adc1ef", kind: "request", text: "401 token_expired on GET /v1/search, token age 4000 s (ttl 3600 s)",
        data: { status: 401, token_age_s: 4000, error_code: "token_expired" } },
      { id: "traffic:window", kind: "traffic", text: "120 requests in the window, 40% errors",
        data: { window: { requests: 120, errors: 48 }, baseline_minutes: 30 } },
      { id: "metric:service:auth", kind: "metric", text: "auth p95 180 ms, no change from baseline",
        data: { p95_ms: 180, error_rate: 0.01 } },
    ],
    missing_info: [],
    report: {
      case_id: "UC4-0001",
      outcome: "RECOMMEND",
      summary: "Likely token_expired: the access token was older than its lifetime.",
      causes: [{
        cause: "token_expired", likelihood: "likely", explanation: "The token age exceeded the TTL at the time of the 401.",
        supporting: [{ evidence_id: "request:c-4261adc1ef", quote: "token age 4000 s (ttl 3600 s)" }],
        contradicting: [],
      }],
      verification_steps: [{ action: "Decode the token and compare exp with the request time.", why: "Shows whether it had expired.",
                             cites: ["request:c-4261adc1ef"] }],
      escalation: { needed: false, team: "", reason: "" },
      missing_info: [],
    },
    report_findings: [],
    groundedness: 1.0,
    generator: "template",
    trace: [
      { step: "load_case", ms: 8.2, detail: "UC4-0001 GET /v1/search" },
      { step: "collect_evidence", ms: 156.97, detail: "3 items, 0 missing" },
      { step: "rank_causes", ms: 38.46, detail: "6 causes ranked" },
    ],
    ...overrides,
  };
}

export function escalateDiagnosis(): Diagnosis {
  const base = recommendDiagnosis();
  return {
    ...base,
    diagnosis_id: "dx-escalate-1",
    case_id: "UC4-0019",
    route: "POST /v1/payments",
    escalate: true,
    failure_class: "authorization",
    class_confidence: 0.985186,
    ranked: [
      cause(1, "ip_not_allowlisted", 0.9673, { status: "likely", escalate: true, failure_class: "authorization",
        first_check: "check_ip_allowlist",
        supporting: [{ signal: "ip_not_allowlisted", present: true, ratio: 4.0, evidence_ids: ["request:c-708ec2622a"] }] }),
      cause(2, "missing_scope", 0.0179, { failure_class: "authorization" }),
    ],
    evidence: [{ id: "request:c-708ec2622a", kind: "request", text: "403 from 203.0.113.x, not allowlisted", data: { status: 403 } }],
    report: {
      ...base.report!,
      case_id: "UC4-0019",
      summary: "Likely ip_not_allowlisted: the client IP is not on the allowlist.",
      causes: [],
      verification_steps: [],
      escalation: { needed: true, team: "payments-api owners",
                    reason: "The first check check_ip_allowlist needs privileged access; a person with that access should run it and decide any fix." },
    },
  };
}

export function clarifyDiagnosis(overrides: Partial<Diagnosis> = {}): Diagnosis {
  return {
    ...recommendDiagnosis(),
    diagnosis_id: "dx-clarify-1",
    case_id: "UC4-0085",
    outcome: "CLARIFY",
    escalate: false,
    failure_class: null,
    class_confidence: null,
    ranked: [],
    evidence: [
      { id: "request:c-0085", kind: "request", text: "503 on GET /v1/orders/{id}", data: {} },
      { id: "missing:dependency-metrics", kind: "missing", text: "No metrics for orders-db in the window", data: { what: "metrics" } },
    ],
    missing_info: ["Metrics for orders-db around the onset"],
    report: null,
    groundedness: 0,
    ...overrides,
  };
}

export function closeCallDiagnosis(): Diagnosis {
  const base = recommendDiagnosis();
  return {
    ...base,
    diagnosis_id: "dx-close-1",
    case_id: "UC4-0006",
    alternatives: ["token_expired", "invalid_api_key"],
    ranked: base.ranked.map((c) => (c.rank <= 2 ? { ...c, near_tie: true, status: "probable", confidence: c.rank === 1 ? 0.51 : 0.47 } : c)),
    tell_apart: {
      causes: ["token_expired", "invalid_api_key"],
      first_checks: { token_expired: "check_token_expiry", invalid_api_key: "check_key_registry" },
      signals: [{ signal: "token_age_over_ttl", favours: "token_expired", p_on: { token_expired: 0.9, invalid_api_key: 0.05 }, observed: null }],
      note: "Check the token age first: it separates the two causes best.",
    },
  };
}

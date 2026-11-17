// Mirrors the backend contract: backend/app/uc4/models.py (Diagnosis, owned by the pipeline team),
// backend/app/uc4/report_models.py (Report) and backend/app/uc4/api.py (envelope, cases, feedback).
// Field names are the backend's own; do not rename them.

export interface Envelope<T> {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
}

/** GET /api/cases item. Evaluation labels are never sent by the backend. */
export interface CaseSummary {
  id: string;
  route: string;
  summary: string;
  split: string;
}

/** GET /health data. */
export interface HealthData {
  api: string; // "up"
  database: string; // "up" | "down"
  pipeline: string; // "ready" | "not_ready"
  pipeline_detail: string;
}

export type Outcome = "RECOMMEND" | "CLARIFY";
export type CauseStatus = "likely" | "probable" | "unsupported";
/** Known evidence kinds; "doc" may be added later and unknown kinds must still render. */
export type EvidenceKind = "request" | "traffic" | "metric" | "change" | "missing" | "doc" | (string & {});

export interface EvidenceItem {
  id: string;
  kind: EvidenceKind;
  text: string;
  data: Record<string, unknown>;
}

export interface SignalLink {
  signal: string;
  present: boolean;
  ratio: number;
  evidence_ids: string[];
}

export interface RankedCause {
  rank: number;
  cause: string;
  failure_class: string;
  confidence: number;
  status: CauseStatus | (string & {});
  near_tie: boolean;
  supporting: SignalLink[];
  contradicting: SignalLink[];
  confirming_seen?: string[];
  confirming_missing?: string[];
  first_check: string | null;
  escalate: boolean;
  missing_info: string[];
}

export interface DistinguishingSignal {
  signal: string;
  favours: string;
  p_on: Record<string, number>;
  observed: boolean | null;
}

export interface TellApart {
  causes: string[];
  first_checks: Record<string, string | null>;
  signals: DistinguishingSignal[];
  note: string;
}

export interface Citation {
  evidence_id: string;
  quote: string;
}

export interface ReportCause {
  cause: string;
  likelihood: string;
  explanation: string;
  supporting: Citation[];
  contradicting: Citation[];
}

export interface VerificationStep {
  action: string;
  why: string;
  cites: string[];
}

export interface Escalation {
  needed: boolean;
  team: string;
  reason: string;
}

export interface Report {
  case_id: string;
  outcome: string;
  summary: string;
  causes: ReportCause[];
  verification_steps: VerificationStep[];
  escalation: Escalation | null;
  missing_info: string[];
}

export interface Finding {
  code: string;
  severity: "info" | "warn" | "block" | (string & {});
  message: string;
  where: string;
}

export interface TraceStep {
  step: string;
  ms: number;
  detail: string;
}

export interface Diagnosis {
  diagnosis_id: string;
  created_at: string;
  case_id: string;
  route: string;
  onset_ts: string;
  outcome: Outcome;
  escalate: boolean;
  failure_class: string | null;
  class_confidence: number | null;
  ranked: RankedCause[];
  alternatives: string[];
  tell_apart: TellApart | null;
  evidence: EvidenceItem[];
  missing_info: string[];
  report: Report | null;
  report_findings: Finding[];
  groundedness: number | null;
  generator: string;
  trace: TraceStep[];
}

export type Verdict = "confirm" | "reject" | "annotate";

export interface FeedbackRequest {
  verdict: Verdict;
  cause_id?: string;
  note?: string;
}

export interface FeedbackRecord {
  feedback_id: string;
  diagnosis_id: string;
  case_id: string;
  verdict: string;
  cause_id: string | null;
  note: string | null;
  created_at: string;
  request_id: string | null;
}

/** GET /api/audit/verify data. */
export interface ChainStatus {
  valid: boolean;
  events_checked: number;
  head_hash: string;
  first_bad_seq: number | null;
  reason: string | null;
}

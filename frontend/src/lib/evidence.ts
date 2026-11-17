import type { Diagnosis, EvidenceItem, RankedCause, SignalLink } from "./types";

export function evidenceIndex(diagnosis: Diagnosis): Map<string, EvidenceItem> {
  return new Map(diagnosis.evidence.map((item) => [item.id, item]));
}

export interface ResolvedRef {
  id: string;
  item: EvidenceItem | null; // null = the diagnosis cites an id that is not in its evidence list
}

export function resolveIds(ids: string[], index: Map<string, EvidenceItem>): ResolvedRef[] {
  return ids.map((id) => ({ id, item: index.get(id) ?? null }));
}

/** Evidence ids a cause relies on, split into supporting and contradicting (de-duplicated, order kept). */
export function causeEvidenceIds(cause: RankedCause): { supporting: string[]; contradicting: string[] } {
  const collect = (links: SignalLink[]) => [...new Set(links.flatMap((l) => l.evidence_ids))];
  return { supporting: collect(cause.supporting), contradicting: collect(cause.contradicting) };
}

/** Every evidence id cited anywhere (ranked signals and report) that is missing from the evidence list. */
export function unresolvedIds(diagnosis: Diagnosis): string[] {
  const index = evidenceIndex(diagnosis);
  const cited = new Set<string>();
  for (const cause of diagnosis.ranked) {
    for (const link of [...cause.supporting, ...cause.contradicting]) link.evidence_ids.forEach((id) => cited.add(id));
  }
  for (const cause of diagnosis.report?.causes ?? []) {
    for (const c of [...cause.supporting, ...cause.contradicting]) cited.add(c.evidence_id);
  }
  for (const step of diagnosis.report?.verification_steps ?? []) step.cites.forEach((id) => cited.add(id));
  return [...cited].filter((id) => !index.has(id));
}

export function sortedCauses(diagnosis: Diagnosis): RankedCause[] {
  return [...diagnosis.ranked].sort((a, b) => a.rank - b.rank);
}

const KIND_LABELS: Record<string, string> = {
  request: "Request", traffic: "Traffic", metric: "Metric", change: "Change", missing: "Missing", doc: "Doc",
};

/** Display name of an evidence kind; unknown future kinds keep their own name. */
export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? (kind || "Unknown");
}

export function evidenceLink(diagnosisId: string, evidenceId: string): string {
  return `/evidence?d=${encodeURIComponent(diagnosisId)}&focus=${encodeURIComponent(evidenceId)}`;
}

/** DOM id for an evidence card (evidence ids contain ":" and "/"). */
export function evidenceAnchor(id: string): string {
  return `ev-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

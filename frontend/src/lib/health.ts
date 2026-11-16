import { ApiError } from "./api";
import type { HealthData } from "./types";

export type HealthState = "healthy" | "not_ready" | "unavailable" | "unknown";

/** Turn GET /health (or its failure) into the three component states. Never guesses "healthy". */
export function deriveHealth(data: HealthData | null, error: unknown):
  { api: HealthState; database: HealthState; pipeline: HealthState } {
  if (!data) {
    // Network/timeout: the API cannot be reached; database and pipeline are then unknown, not "down".
    const unreachable = error instanceof ApiError && error.kind !== "aborted";
    return { api: unreachable ? "unavailable" : "unknown", database: "unknown", pipeline: "unknown" };
  }
  return {
    api: data.api === "up" ? "healthy" : "unavailable",
    database: data.database === "up" ? "healthy" : data.database === "down" ? "unavailable" : "unknown",
    pipeline: data.pipeline === "ready" ? "healthy" : data.pipeline === "not_ready" ? "not_ready" : "unknown",
  };
}

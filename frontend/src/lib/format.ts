// Display-only formatting. Never changes the underlying values.

/** Akshay's rule: > 0.99 shows "> 0.99", < 0.01 shows "< 0.01", otherwise two decimals. */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value > 0.99) return "> 0.99";
  if (value < 0.01) return "< 0.01";
  return value.toFixed(2);
}

/** Bar width in percent, clamped to 0..100 (display only). */
export function confidenceWidth(value: number | null | undefined): number {
  if (value === null || value === undefined || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, value * 100));
}

export function formatRatio(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `×${value >= 10 ? value.toFixed(0) : value.toFixed(1)}`;
}

export function formatMs(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  return ms < 1 ? "< 1 ms" : `${ms < 100 ? ms.toFixed(1) : Math.round(ms)} ms`;
}

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  timeZone: "UTC", hour12: false,
});

/** ISO timestamp -> "16 Nov 2026, 10:00:00 UTC". Unparseable input is shown as given. */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${dateFormat.format(date)} UTC`;
}

export function formatClock(date: Date): string {
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** "token_expired" -> "Token expired" (identifiers are still shown in mono next to it). */
export function humanize(identifier: string | null | undefined): string {
  if (!identifier) return "—";
  const text = identifier.replace(/[_-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Split "GET /v1/orders/{id}" into method and path. */
export function splitRoute(route: string): { method: string; path: string } {
  const match = /^([A-Z]+)\s+(.*)$/.exec(route.trim());
  return match ? { method: match[1], path: match[2] } : { method: "", path: route };
}

export function shortHash(hash: string | null | undefined, size = 12): string {
  if (!hash) return "—";
  return hash.length > size ? `${hash.slice(0, size)}…` : hash;
}

/** Who wrote the report text, from the backend's generator field (today always "template"). */
export function generatorLabel(generator: string | null | undefined): string {
  if (!generator) return "Generator unknown";
  return generator === "template" ? "Written by template" : `Written by ${generator}`;
}

/** Render any evidence data value as plain text (never HTML). */
export function valueToText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

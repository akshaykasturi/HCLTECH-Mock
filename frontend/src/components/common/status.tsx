import { AlertOctagon, CheckCircle2, CircleDashed, Clock3, HelpCircle, ShieldAlert } from "lucide-react";
import { confidenceWidth, formatConfidence } from "../../lib/format";
import type { HealthState } from "../../lib/health";
import { Badge, type Tone } from "./ui";

const healthLabel: Record<HealthState, string> = {
  healthy: "Healthy", not_ready: "Not ready", unavailable: "Unavailable", unknown: "Unknown",
};
const healthTone: Record<HealthState, Tone> = {
  healthy: "success", not_ready: "warning", unavailable: "danger", unknown: "neutral",
};

export function HealthBadge({ state, label }: { state: HealthState; label?: string }) {
  const Icon = { healthy: CheckCircle2, not_ready: Clock3, unavailable: AlertOctagon, unknown: HelpCircle }[state];
  return <Badge tone={healthTone[state]} icon={<Icon className="h-3.5 w-3.5" aria-hidden />}>{label ?? healthLabel[state]}</Badge>;
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  if (outcome === "RECOMMEND") {
    return <Badge tone="primary" icon={<CheckCircle2 className="h-3.5 w-3.5" aria-hidden />}>RECOMMEND</Badge>;
  }
  if (outcome === "CLARIFY") {
    return <Badge tone="warning" icon={<CircleDashed className="h-3.5 w-3.5" aria-hidden />}>CLARIFY</Badge>;
  }
  return <Badge>{outcome}</Badge>;
}

export function EscalateBadge() {
  return (
    <Badge tone="danger" icon={<ShieldAlert className="h-3.5 w-3.5" aria-hidden />}
           title="The first check needs privileged access: a person with that access should run it">
      Escalate
    </Badge>
  );
}

/** Cause statuses are likely / probable / unsupported. Anything else is shown as "Unrated", never as confirmed. */
export function CauseStatusBadge({ status }: { status: string }) {
  const map: Record<string, { tone: Tone; label: string; title: string }> = {
    likely: { tone: "primary", label: "Likely",
              title: "All confirming signals seen and confidence above the threshold. Still not confirmed until a reviewer runs the first check." },
    probable: { tone: "warning", label: "Probable", title: "Confidence above the threshold, but not every confirming signal was seen." },
    unsupported: { tone: "neutral", label: "Unsupported", title: "Not enough support from the evidence." },
  };
  const item = map[status] ?? { tone: "neutral" as Tone, label: "Unrated", title: "Unknown status from the backend." };
  return <Badge tone={item.tone} title={item.title}>{item.label}</Badge>;
}

export function ConfidenceBar({ value, label = "Confidence" }: { value: number | null; label?: string }) {
  const text = formatConfidence(value);
  return (
    <div className="flex items-center gap-2" title="Model confidence, not certainty">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200" role="meter" aria-label={label}
           aria-valuemin={0} aria-valuemax={1} aria-valuenow={value ?? undefined} aria-valuetext={text}>
        <div className="h-full rounded-full bg-primary" style={{ width: `${confidenceWidth(value)}%` }} />
      </div>
      <span className="font-mono text-xs tabular-nums text-slate-700">{text}</span>
    </div>
  );
}

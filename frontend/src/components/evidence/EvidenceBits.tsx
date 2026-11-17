import { Link } from "react-router-dom";
import { Activity, AlertTriangle, BookOpen, FileQuestion, GitCommitHorizontal, Network, Send, Tag } from "lucide-react";
import { evidenceLink, kindLabel } from "../../lib/evidence";
import type { EvidenceItem } from "../../lib/types";
import { Badge, type Tone } from "../common/ui";

const KIND_STYLE: Record<string, { tone: Tone; Icon: typeof Tag }> = {
  request: { tone: "primary", Icon: Send },
  traffic: { tone: "neutral", Icon: Network },
  metric: { tone: "success", Icon: Activity },
  change: { tone: "warning", Icon: GitCommitHorizontal },
  missing: { tone: "danger", Icon: FileQuestion },
  doc: { tone: "neutral", Icon: BookOpen },
};

/** Badge for an evidence kind; unknown future kinds get a neutral tag with their own name. */
export function KindBadge({ kind }: { kind: string }) {
  const style = KIND_STYLE[kind] ?? { tone: "neutral" as Tone, Icon: Tag };
  return <Badge tone={style.tone} icon={<style.Icon className="h-3.5 w-3.5" aria-hidden />}>{kindLabel(kind)}</Badge>;
}

/** A citation of an evidence id: a link into the Evidence Explorer, or a warning when the id is not in the diagnosis. */
export function EvidenceRef({ id, item, diagnosisId }: { id: string; item: EvidenceItem | null; diagnosisId: string }) {
  if (!item) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-warning-soft px-1.5 py-0.5 font-mono text-xs text-warning-text"
            title="This evidence id is cited but is not in the diagnosis evidence list">
        <AlertTriangle className="h-3 w-3" aria-hidden />
        {id}
        <span className="sr-only"> (not found in this diagnosis)</span>
      </span>
    );
  }
  return (
    <Link to={evidenceLink(diagnosisId, id)} title={item.text}
          className="inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-primary underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
      {id}
    </Link>
  );
}

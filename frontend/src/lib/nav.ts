import { Activity, ClipboardCheck, FileSearch, FolderSearch, LayoutDashboard, ScrollText, Stethoscope } from "lucide-react";

export const NAV_ITEMS = [
  { to: "/", label: "Dashboard", Icon: LayoutDashboard, end: true },
  { to: "/cases", label: "Case Explorer", Icon: FolderSearch, end: false },
  { to: "/diagnosis", label: "Diagnosis", Icon: Stethoscope, end: false },
  { to: "/evidence", label: "Evidence Explorer", Icon: FileSearch, end: false },
  { to: "/review", label: "Human Review", Icon: ClipboardCheck, end: false },
  { to: "/audit", label: "Audit History", Icon: ScrollText, end: false },
  { to: "/system-health", label: "System Health", Icon: Activity, end: false },
] as const;

/** Breadcrumb trail for a path (labels only; the last item is the current page). */
export function breadcrumbs(pathname: string): { label: string; to?: string }[] {
  const crumbs: { label: string; to?: string }[] = [{ label: "UC4", to: "/" }];
  if (pathname === "/") return [...crumbs, { label: "Dashboard" }];
  const [first, second] = pathname.split("/").filter(Boolean);
  if (first === "diagnoses" && second) {
    return [...crumbs, { label: "Diagnosis", to: "/diagnosis" }, { label: decodeURIComponent(second) }];
  }
  const item = NAV_ITEMS.find((n) => n.to === `/${first}`);
  if (!item) return [...crumbs, { label: "Not found" }];
  if (second) return [...crumbs, { label: item.label, to: item.to }, { label: decodeURIComponent(second) }];
  return [...crumbs, { label: item.label }];
}

/**
 * <StatusBadge> — domain-aware status pill driven by statusEngine.
 * Single source of truth for status → label/color mapping (per STANDARDS §11
 * and audit §3.6 — replaces 3 different status dicts that drifted in v1).
 */

import { statusEngine, type StatusDomain } from "@/engines/statusEngine";
import { cn } from "@/lib/utils";

const COLOR_CLASSES = {
  primary: "bg-primary/15 text-primary border-primary/30",
  secondary: "bg-secondary/15 text-secondary border-secondary/30",
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  error: "bg-danger/15 text-danger border-danger/30",
  neutral: "bg-card text-text-muted border-border",
} as const;

export function StatusBadge({
  domain,
  status,
  className,
}: {
  domain: StatusDomain;
  status: string;
  className?: string;
}) {
  const def = statusEngine.resolve(domain, status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border px-2 py-0.5 text-[10px] font-semibold",
        COLOR_CLASSES[def.color],
        className,
      )}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {def.label}
    </span>
  );
}

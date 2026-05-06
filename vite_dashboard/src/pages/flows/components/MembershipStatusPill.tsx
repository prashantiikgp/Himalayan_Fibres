/**
 * <MembershipStatusPill> — visual mapping of the 6 FlowMembership
 * statuses to tone + icon (PLAN_flows §3.5).
 *
 * `paused` and `stopped` share the same tone but use different icons
 * so operators can tell a reversible state from a terminal one at a
 * glance.
 */

import type { MembershipStatus } from "@/api/flows";
import { cn } from "@/lib/utils";

const SPEC: Record<
  MembershipStatus,
  { tone: string; icon: string; label: string }
> = {
  active: {
    tone: "border-primary/40 bg-primary/10 text-primary",
    icon: "▶",
    label: "Active",
  },
  waiting_event: {
    tone: "border-warning/40 bg-warning/10 text-warning",
    icon: "⏸",
    label: "Waiting event",
  },
  paused: {
    tone: "border-border bg-card text-text-muted",
    icon: "⏯",
    label: "Paused",
  },
  completed: {
    tone: "border-success/40 bg-success/10 text-success",
    icon: "✓",
    label: "Completed",
  },
  failed: {
    tone: "border-danger/40 bg-danger/10 text-danger",
    icon: "⚠",
    label: "Failed",
  },
  stopped: {
    tone: "border-border bg-card text-text-muted",
    icon: "⊘",
    label: "Stopped",
  },
};

export function MembershipStatusPill({
  status,
}: {
  status: MembershipStatus | string;
}) {
  const spec = SPEC[status as MembershipStatus];
  if (!spec) {
    return (
      <span className="inline-block rounded-pill border border-border bg-card px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-text-muted">
        {status}
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        spec.tone,
      )}
    >
      <span aria-hidden>{spec.icon}</span>
      <span>{spec.label}</span>
    </span>
  );
}

/**
 * <CostEstimateCards> — three-card cost preview strip for Compose tab.
 */

import type { CostEstimateResponse } from "@/api/broadcasts";
import { formatDuration } from "@/lib/format";

export function CostEstimateCards({
  data,
  isLoading,
}: {
  data: CostEstimateResponse | undefined;
  isLoading: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Card label="Recipients" value={isLoading ? "…" : String(data?.recipients ?? 0)} />
      <Card label="Per message" value={isLoading ? "…" : data?.per_message_display ?? "—"} />
      <Card label="Total" value={isLoading ? "…" : data?.total_display ?? "—"} primary />
      <Card
        label="Est. delivery"
        value={
          isLoading
            ? "…"
            : data?.est_delivery_seconds
            ? formatDuration(data.est_delivery_seconds)
            : "—"
        }
      />
    </div>
  );
}

function Card({
  label,
  value,
  primary,
}: {
  label: string;
  value: string;
  primary?: boolean;
}) {
  return (
    <div className="flex flex-col rounded-lg border border-border bg-card/40 p-3">
      <span className="text-[10px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span
        className={
          primary ? "text-lg font-semibold text-primary" : "text-base font-medium text-text"
        }
      >
        {value}
      </span>
    </div>
  );
}

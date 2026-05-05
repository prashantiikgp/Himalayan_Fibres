/**
 * <AudienceFunnel> — sticky header on the Compose tab.
 *
 * **B3 fix lives here.** v1's audience KPIs were buried in a left-column
 * funnel under all the filters; the team didn't see "how many people
 * am I targeting" without scrolling. v2 surfaces that count + segment
 * name as a prominent pill at the top of the Compose tab. As filters
 * change the headline re-renders.
 */

import type {
  AudienceBreakdownItem,
  AudiencePreviewResponse,
} from "@/api/broadcasts";

export function AudienceFunnel({
  data,
  isLoading,
  segmentLabel,
}: {
  data: AudiencePreviewResponse | undefined;
  isLoading: boolean;
  segmentLabel: string;
}) {
  return (
    <div className="sticky top-0 z-10 flex flex-col gap-2 rounded-lg border border-border bg-card/80 p-card backdrop-blur">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-xs uppercase tracking-wider text-text-muted">Targeting</span>
        <span className="text-2xl font-semibold text-text">
          {isLoading ? "…" : data?.final_recipients ?? 0}
        </span>
        <span className="text-sm text-text-muted">recipient{data?.final_recipients === 1 ? "" : "s"}</span>
        <span className="text-sm text-text-muted">in</span>
        <span className="rounded-pill border border-primary/40 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
          {segmentLabel}
        </span>
      </div>

      {data && (
        <div className="grid grid-cols-2 gap-2 text-[11px] text-text-muted sm:grid-cols-5">
          <Counter label="In segment" value={data.total_in_segment} />
          <Counter label="Eligible on channel" value={data.eligible_on_channel} />
          <Counter label="Final" value={data.final_recipients} highlight />
          <Counter label="Channel-excluded" value={data.excluded_by_channel} />
          <Counter label="Filter-excluded" value={data.excluded_by_filters} />
        </div>
      )}

      {data && data.lifecycle.length > 0 && (
        <div className="flex flex-wrap gap-1 text-[10px]">
          <Chips title="Lifecycle" items={data.lifecycle} />
          <Chips title="Country" items={data.geography} />
          <Chips title="Consent" items={data.consent} />
        </div>
      )}
    </div>
  );
}

function Counter({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className={highlight ? "text-base font-semibold text-success" : "text-sm text-text"}>
        {value}
      </span>
      <span>{label}</span>
    </div>
  );
}

function Chips({
  title,
  items,
}: {
  title: string;
  items: AudienceBreakdownItem[];
}) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="uppercase tracking-wider text-text-muted">{title}:</span>
      {items.slice(0, 4).map((it) => (
        <span
          key={it.label}
          className="rounded-pill border border-border bg-card px-2 py-0.5 text-text"
        >
          {it.label} <span className="text-text-muted">{it.count}</span>
        </span>
      ))}
    </div>
  );
}

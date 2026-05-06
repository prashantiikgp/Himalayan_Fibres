/**
 * <FlowsTable> — list of automation flows with trigger pill + active count.
 *
 * Phase 7.8: row click navigates to /flows/:id (replaces the inline
 * cohort-runs panel from Phase 5.0). The legacy useFlowRuns hook stays
 * in api/flows.ts for backward compat but no UI consumes it.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/tables/DataTable";
import {
  useFlows,
  type FlowOut,
  type FlowChannel,
} from "@/api/flows";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

export function FlowsTable() {
  const [activeOnly, setActiveOnly] = useState(false);
  const [channel, setChannel] =
    useState<"all" | "email" | "whatsapp" | "multi">("all");
  const navigate = useNavigate();
  const { data, isLoading, error } = useFlows({
    active_only: activeOnly,
    channel: channel === "all" ? undefined : channel,
  });

  const columns = useMemo<ColumnDef<FlowOut, unknown>[]>(
    () => [
      {
        accessorKey: "is_active",
        header: "Status",
        cell: ({ row }) => <ActivePill active={row.original.is_active} />,
      },
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium text-text">{row.original.name}</span>
            {row.original.description && (
              <span className="line-clamp-2 text-xs text-text-muted">
                {row.original.description}
              </span>
            )}
          </div>
        ),
      },
      {
        accessorKey: "trigger_type",
        header: "Trigger",
        cell: ({ row }) => (
          <TriggerPill
            triggerType={row.original.trigger_type}
            triggerConfig={row.original.trigger_config}
          />
        ),
      },
      {
        accessorKey: "channel",
        header: "Channel",
        cell: ({ row }) => <ChannelPill channel={row.original.channel} />,
      },
      {
        accessorKey: "step_count",
        header: "Steps",
        cell: ({ row }) => (
          <span className="text-text">{row.original.step_count}</span>
        ),
      },
      {
        accessorKey: "active_count",
        header: "Active",
        cell: ({ row }) => (
          <span
            className={cn(
              "tabular-nums",
              row.original.active_count > 0 ? "text-text" : "text-text-muted",
            )}
          >
            {row.original.active_count}
          </span>
        ),
      },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ row }) => formatRelative(row.original.created_at),
      },
    ],
    [],
  );

  return (
    <div className="flex flex-col gap-3 p-card">
      <div className="flex items-center gap-3">
        <div className="ml-auto flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
              className="rounded border-border"
            />
            Active only
          </label>
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value as typeof channel)}
            className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
          >
            <option value="all">All channels</option>
            <option value="email">Email</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="multi">Multi</option>
          </select>
        </div>
      </div>

      <DataTable
        data={data?.flows ?? []}
        columns={columns}
        isLoading={isLoading}
        error={error}
        getRowId={(row) => String(row.id)}
        onRowClick={(row) => navigate(`/flows/${row.id}`)}
        emptyMessage="No flows match these filters."
      />
    </div>
  );
}

function ActivePill({ active }: { active: boolean }) {
  return (
    <span
      className={cn(
        "inline-block rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        active
          ? "border-success/40 bg-success/10 text-success"
          : "border-border bg-card text-text-muted",
      )}
    >
      {active ? "Active" : "Inactive"}
    </span>
  );
}

export function ChannelPill({ channel }: { channel: FlowChannel | string }) {
  const tone =
    channel === "whatsapp"
      ? "border-success/40 bg-success/10 text-success"
      : channel === "multi"
      ? "border-purple-500/40 bg-purple-500/10 text-purple-500"
      : "border-primary/40 bg-primary/10 text-primary";
  const label =
    channel === "whatsapp"
      ? "WhatsApp"
      : channel === "multi"
      ? "Multi"
      : "Email";
  return (
    <span
      className={cn(
        "inline-block rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        tone,
      )}
    >
      {label}
    </span>
  );
}

/**
 * Renders the trigger as a pill: "Manual", "Lifecycle: customer",
 * "Tag: samples_requested". Falls back to the raw type for unknown
 * trigger kinds rather than failing.
 */
export function TriggerPill({
  triggerType,
  triggerConfig,
}: {
  triggerType: string;
  triggerConfig: Record<string, unknown>;
}) {
  let label: string;
  let tone: string;

  if (triggerType === "manual") {
    label = "Manual";
    tone = "border-border bg-card text-text-muted";
  } else if (triggerType === "lifecycle") {
    const to = triggerConfig?.to ?? triggerConfig?.lifecycle;
    const value = Array.isArray(to) ? to.join(" / ") : (to ?? "?");
    label = `Lifecycle: ${value}`;
    tone = "border-primary/40 bg-primary/10 text-primary";
  } else if (triggerType === "tag") {
    const tag = triggerConfig?.tag ?? "?";
    label = `Tag: ${tag}`;
    tone = "border-warning/40 bg-warning/10 text-warning";
  } else {
    label = triggerType;
    tone = "border-border bg-card text-text-muted";
  }

  return (
    <span
      className={cn(
        "inline-block rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        tone,
      )}
    >
      {label}
    </span>
  );
}

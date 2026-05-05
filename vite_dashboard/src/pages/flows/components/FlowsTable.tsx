/**
 * <FlowsTable> — read-only list of automation flows.
 *
 * Phase 5.0 ships read-only. Phase 5.1+ will add Start/Pause/Cancel
 * actions and a per-flow detail drawer with the steps editor.
 */

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/tables/DataTable";
import { useFlowRuns, useFlows, type FlowOut } from "@/api/flows";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

export function FlowsTable() {
  const [activeOnly, setActiveOnly] = useState(false);
  const [channel, setChannel] = useState<"all" | "email" | "whatsapp">("all");
  const { data, isLoading, error } = useFlows({
    active_only: activeOnly,
    channel: channel === "all" ? undefined : channel,
  });
  const [openFlow, setOpenFlow] = useState<FlowOut | null>(null);

  const columns = useMemo<ColumnDef<FlowOut, unknown>[]>(
    () => [
      {
        accessorKey: "is_active",
        header: "Status",
        cell: ({ row }) => (
          <ActivePill active={row.original.is_active} />
        ),
      },
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium text-text">{row.original.name}</span>
            {row.original.description && (
              <span className="truncate text-xs text-text-muted">
                {row.original.description}
              </span>
            )}
          </div>
        ),
      },
      {
        accessorKey: "channel",
        header: "Channel",
        cell: ({ row }) => (
          <ChannelPill channel={row.original.channel} />
        ),
      },
      {
        accessorKey: "step_count",
        header: "Steps",
        cell: ({ row }) => row.original.step_count,
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
        {/* Phase 6.5: page title moved to HowToUse accordion above. */}
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
          </select>
        </div>
      </div>

      <DataTable
        data={data?.flows ?? []}
        columns={columns}
        isLoading={isLoading}
        error={error}
        getRowId={(row) => String(row.id)}
        onRowClick={(row) => setOpenFlow(row)}
        emptyMessage="No flows match these filters."
      />

      {openFlow && (
        <FlowRunsPanel flow={openFlow} onClose={() => setOpenFlow(null)} />
      )}
    </div>
  );
}

function FlowRunsPanel({
  flow,
  onClose,
}: {
  flow: FlowOut;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useFlowRuns(flow.id, 20);

  return (
    <div className="rounded-lg border border-border bg-card/40 p-card">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text">
          Recent runs — {flow.name}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-text-muted hover:text-text"
        >
          Close
        </button>
      </div>
      {isLoading && <p className="text-xs text-text-muted">Loading runs…</p>}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error.message}
        </p>
      )}
      {data && data.runs.length === 0 && (
        <p className="text-xs text-text-muted">No runs yet.</p>
      )}
      {data && data.runs.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-text-muted">
            <tr className="border-b border-border/40">
              <th className="py-1 text-left font-medium">Started</th>
              <th className="py-1 text-left font-medium">Segment</th>
              <th className="py-1 text-left font-medium">Step</th>
              <th className="py-1 text-left font-medium">Status</th>
              <th className="py-1 text-right font-medium">Sent</th>
              <th className="py-1 text-right font-medium">Failed</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((r) => (
              <tr key={r.id} className="border-b border-border/20">
                <td className="py-1 text-text">{formatRelative(r.started_at)}</td>
                <td className="py-1 text-text-muted">{r.segment_id ?? "—"}</td>
                <td className="py-1 text-text">{r.current_step + 1}</td>
                <td className="py-1">
                  <RunStatusPill status={r.status} />
                </td>
                <td className="py-1 text-right text-text">{r.total_sent}</td>
                <td className="py-1 text-right">
                  <span className={r.total_failed > 0 ? "text-danger" : ""}>
                    {r.total_failed}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
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

function ChannelPill({ channel }: { channel: "email" | "whatsapp" }) {
  const isWa = channel === "whatsapp";
  return (
    <span
      className={cn(
        "inline-block rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        isWa
          ? "border-success/40 bg-success/10 text-success"
          : "border-primary/40 bg-primary/10 text-primary",
      )}
    >
      {isWa ? "WhatsApp" : "Email"}
    </span>
  );
}

function RunStatusPill({ status }: { status: string }) {
  const lower = status.toLowerCase();
  const tone =
    lower === "active"
      ? "primary"
      : lower === "completed"
      ? "success"
      : lower === "failed" || lower === "cancelled"
      ? "danger"
      : "muted";
  const cls: Record<string, string> = {
    success: "border-success/40 bg-success/10 text-success",
    danger: "border-danger/40 bg-danger/10 text-danger",
    primary: "border-primary/40 bg-primary/10 text-primary",
    muted: "border-border bg-card text-text-muted",
  };
  return (
    <span
      className={cn(
        "rounded-pill border px-2 py-0.5 text-[9px] font-medium uppercase tracking-wider",
        cls[tone],
      )}
    >
      {status}
    </span>
  );
}

/**
 * <PerformanceTab> — per-broadcast KPIs + paginated recipient list.
 *
 * Phase 3.1b.3 ships the **B16 fix**. v1's recipient table silently
 * capped at 100 rows; this version paginates by id-cursor with no
 * implicit cap. Pick a broadcast from the History tab → its id flows
 * here via `?broadcast_id=...`.
 */

import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import {
  useBroadcastDetail,
  useBroadcastRecipients,
  useBroadcastsList,
  type RecipientItem,
} from "@/api/broadcasts";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "sent", label: "Sent" },
  { value: "failed", label: "Failed" },
  { value: "queued", label: "Queued" },
];

export function PerformanceTab() {
  const [params, setParams] = useSearchParams();
  const broadcastId = params.get("broadcast_id");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [cursor, setCursor] = useState<number | null>(null);

  const { data: detail, isLoading: detailLoading, error: detailError } =
    useBroadcastDetail(broadcastId);
  const { data: recipients, isFetching } = useBroadcastRecipients(
    broadcastId,
    cursor,
    100,
    statusFilter,
  );

  // For the dropdown — last 100 broadcasts.
  const { data: list } = useBroadcastsList({ page_size: 100 });

  function selectBroadcast(id: string) {
    const next = new URLSearchParams(params);
    next.set("broadcast_id", id);
    setParams(next, { replace: true });
    setCursor(null);
    setStatusFilter("all");
  }

  const columns = useMemo<ColumnDef<RecipientItem, unknown>[]>(
    () => [
      {
        accessorKey: "address",
        header: "Recipient",
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="text-text">{row.original.address || row.original.contact_id}</span>
            <span className="text-[10px] text-text-muted">{row.original.contact_id}</span>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusPill status={row.original.status} />,
      },
      {
        accessorKey: "sent_at",
        header: "Sent at",
        cell: ({ row }) =>
          row.original.sent_at ? formatRelative(row.original.sent_at) : "—",
      },
      {
        accessorKey: "error_message",
        header: "Error",
        cell: ({ row }) =>
          row.original.error_message ? (
            <span className="text-xs text-danger">{row.original.error_message}</span>
          ) : (
            "—"
          ),
      },
    ],
    [],
  );

  return (
    <div className="flex flex-col gap-3 p-card">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
          Performance
        </h2>
        <select
          value={broadcastId ?? ""}
          onChange={(e) => e.target.value && selectBroadcast(e.target.value)}
          className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
        >
          <option value="">— Pick a broadcast —</option>
          {list?.broadcasts.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name} ({b.channel})
            </option>
          ))}
        </select>
      </header>

      {!broadcastId && (
        <p className="rounded-md border border-dashed border-border bg-card/40 p-card text-sm text-text-muted">
          Pick a broadcast above (or click one in the History tab) to see its
          KPIs and recipient list.
        </p>
      )}

      {broadcastId && detailLoading && (
        <p className="text-sm text-text-muted">Loading…</p>
      )}
      {broadcastId && detailError && (
        <p role="alert" className="text-sm text-danger">{detailError.message}</p>
      )}

      {detail && (
        <>
          <KpiStrip
            recipients={detail.total_recipients}
            sent={detail.total_sent}
            failed={detail.total_failed}
            status={detail.status}
            channel={detail.channel}
          />

          <div className="flex items-center justify-between gap-2">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCursor(null);
              }}
              className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            {recipients && (
              <span className="text-xs text-text-muted">
                Showing {recipients.recipients.length} of {recipients.total}
                {recipients.next_cursor !== null && " (more available)"}
              </span>
            )}
          </div>

          <DataTable
            data={recipients?.recipients ?? []}
            columns={columns}
            isLoading={isFetching}
            getRowId={(r) => String(r.id)}
            emptyMessage="No recipients match this filter."
          />

          {recipients?.next_cursor !== null && recipients?.next_cursor !== undefined && (
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setCursor(recipients.next_cursor)}
              >
                Load next 100
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function KpiStrip({
  recipients,
  sent,
  failed,
  status,
  channel,
}: {
  recipients: number;
  sent: number;
  failed: number;
  status: string;
  channel: string;
}) {
  const successRate = recipients ? Math.round((sent / recipients) * 100) : 0;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      <KpiCard label="Status" value={status} />
      <KpiCard label="Channel" value={channel} />
      <KpiCard label="Recipients" value={String(recipients)} />
      <KpiCard label="Sent" value={String(sent)} success />
      <KpiCard
        label="Failed"
        value={`${failed} (${100 - successRate}%)`}
        danger={failed > 0}
      />
    </div>
  );
}

function KpiCard({
  label,
  value,
  success,
  danger,
}: {
  label: string;
  value: string;
  success?: boolean;
  danger?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border p-3",
        danger
          ? "border-danger/40 bg-danger/10"
          : success
          ? "border-success/40 bg-success/10"
          : "border-border bg-card/40",
      )}
    >
      <span className="text-[10px] uppercase tracking-wider text-text-muted">{label}</span>
      <span
        className={cn(
          "text-lg font-medium",
          danger ? "text-danger" : success ? "text-success" : "text-text",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const lower = status.toLowerCase();
  const tone =
    lower === "sent"
      ? "success"
      : lower === "failed"
      ? "danger"
      : "muted";
  const cls: Record<string, string> = {
    success: "border-success/40 bg-success/10 text-success",
    danger: "border-danger/40 bg-danger/10 text-danger",
    muted: "border-border bg-card text-text-muted",
  };
  return (
    <span className={cn("inline-block rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider", cls[tone])}>
      {status}
    </span>
  );
}

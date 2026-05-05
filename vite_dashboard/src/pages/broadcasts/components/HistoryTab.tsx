/**
 * <HistoryTab> — unified table of WhatsApp + Email broadcasts.
 *
 * Bug fix wired by construction:
 *  - **B6** (history Email channel filter empty in v1): the table reads
 *    from `/api/v2/broadcasts` which queries both `broadcasts` and
 *    `campaigns` tables, so picking `channel=email` actually returns
 *    email rows. v1 only read from `broadcasts`.
 */

import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/tables/DataTable";
import { useDebouncedValue } from "@/lib/hooks";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";
import {
  useBroadcastsList,
  type BroadcastChannel,
  type BroadcastListItem,
} from "@/api/broadcasts";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const CHANNEL_OPTIONS: { value: "all" | BroadcastChannel; label: string }[] = [
  { value: "all", label: "All channels" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
];

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "scheduled", label: "Scheduled" },
  { value: "sending", label: "Sending" },
  { value: "sent", label: "Sent" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

export function HistoryTab() {
  const [params, setParams] = useSearchParams();
  const channel = (params.get("channel") as BroadcastChannel | "all" | null) ?? "all";
  const statusFilter = params.get("status") ?? "all";
  const [search, setSearch] = useState(params.get("search") ?? "");
  const debouncedSearch = useDebouncedValue(search, 250);

  function setUrl(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  }

  const { data, isLoading, error } = useBroadcastsList({
    channel: channel === "all" ? undefined : channel,
    status: statusFilter === "all" ? undefined : statusFilter,
    search: debouncedSearch || undefined,
    page_size: 100,
  });

  const columns = useMemo<ColumnDef<BroadcastListItem, unknown>[]>(
    () => [
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusPill status={row.original.status} />,
      },
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
          <span className="font-medium text-text">{row.original.name}</span>
        ),
      },
      {
        accessorKey: "channel",
        header: "Channel",
        cell: ({ row }) => <ChannelPill channel={row.original.channel} />,
      },
      {
        accessorKey: "template_id",
        header: "Template",
        cell: ({ row }) =>
          row.original.template_id ? (
            <code className="text-xs text-text-subtle">{row.original.template_id}</code>
          ) : (
            <span className="text-text-muted">—</span>
          ),
      },
      {
        accessorKey: "total_sent",
        header: "Sent",
        cell: ({ row }) => row.original.total_sent,
      },
      {
        accessorKey: "total_failed",
        header: "Failed",
        cell: ({ row }) => (
          <span className={row.original.total_failed > 0 ? "text-danger" : ""}>
            {row.original.total_failed}
          </span>
        ),
      },
      {
        accessorKey: "sent_at",
        header: "Sent at",
        cell: ({ row }) =>
          row.original.sent_at ? formatRelative(row.original.sent_at) : "—",
      },
    ],
    [],
  );

  return (
    <div className="flex flex-col gap-3 p-card">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[2fr_1fr_1fr]">
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-text-muted" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setUrl("search", e.target.value);
            }}
            placeholder="Search by broadcast name…"
            className="pl-8"
          />
        </div>
        <Select
          label="Channel"
          value={channel}
          options={CHANNEL_OPTIONS}
          onChange={(v) => setUrl("channel", v)}
        />
        <Select
          label="Status"
          value={statusFilter}
          options={STATUS_OPTIONS}
          onChange={(v) => setUrl("status", v)}
        />
      </div>

      <DataTable
        data={data?.broadcasts ?? []}
        columns={columns}
        isLoading={isLoading}
        error={error}
        getRowId={(row) => row.id}
        onRowClick={(row) => {
          const next = new URLSearchParams(params);
          next.set("tab", "performance");
          next.set("broadcast_id", row.id);
          setParams(next, { replace: true });
        }}
        emptyMessage="No broadcasts match these filters."
      />

      {data && (
        <p className="text-xs text-text-muted">
          {data.total} broadcast{data.total === 1 ? "" : "s"} total
          {channel !== "all" && ` (${channel})`}
        </p>
      )}
    </div>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-text-muted">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function StatusPill({ status }: { status: string }) {
  const lower = status.toLowerCase();
  const tone = (() => {
    if (lower === "sent" || lower === "completed") return "success";
    if (lower === "failed") return "danger";
    if (lower === "sending") return "primary";
    if (lower === "scheduled") return "warning";
    return "muted";
  })();
  const cls: Record<string, string> = {
    success: "border-success/40 bg-success/10 text-success",
    danger: "border-danger/40 bg-danger/10 text-danger",
    primary: "border-primary/40 bg-primary/10 text-primary",
    warning: "border-warning/40 bg-warning/10 text-warning",
    muted: "border-border bg-card text-text-muted",
  };
  return (
    <span className={cn("inline-block rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider", cls[tone])}>
      {status}
    </span>
  );
}

function ChannelPill({ channel }: { channel: BroadcastChannel }) {
  const isWa = channel === "whatsapp";
  return (
    <span
      className={cn(
        "inline-block rounded-pill border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        isWa ? "border-success/40 bg-success/10 text-success" : "border-primary/40 bg-primary/10 text-primary",
      )}
    >
      {isWa ? "WhatsApp" : "Email"}
    </span>
  );
}

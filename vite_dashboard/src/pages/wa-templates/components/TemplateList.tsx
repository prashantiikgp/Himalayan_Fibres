/**
 * <TemplateList> — left panel of the Template Studio.
 *
 * Drops v1's folder-tree visualization (audit-recommended) and renders
 * a flat searchable list with status + tier columns. Selecting a row
 * loads it into the editor on the right via the parent `onSelect`.
 */

import { useState } from "react";
import { Search, Plus, RefreshCw } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useDebouncedValue } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { useSyncTemplates, useWaTemplates, type WATemplateOut } from "@/api/wa";
import { useJobProgress } from "@/api/broadcasts";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "DRAFT", label: "Draft" },
  { value: "PENDING", label: "Pending" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
];

const TIER_OPTIONS = [
  { value: "all", label: "All tiers" },
  { value: "company", label: "Company" },
  { value: "category", label: "Category" },
  { value: "product", label: "Product" },
  { value: "utility", label: "Utility" },
];

export function TemplateList({
  selectedId,
  onSelect,
  onCreateNew,
}: {
  selectedId: number | null;
  onSelect: (id: number) => void;
  onCreateNew: () => void;
}) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [tier, setTier] = useState<string>("all");
  const debounced = useDebouncedValue(search, 250);
  const [syncJobId, setSyncJobId] = useState<string | null>(null);
  const [confirmSync, setConfirmSync] = useState(false);
  const syncMutation = useSyncTemplates();
  const { data: syncJob } = useJobProgress(syncJobId);
  const syncing =
    syncMutation.isPending ||
    (syncJob && (syncJob.status === "queued" || syncJob.status === "running"));

  function performSync() {
    syncMutation.mutate(undefined, {
      onSuccess: (res) => {
        setSyncJobId(res.job_id);
        setConfirmSync(false);
      },
      onError: () => setConfirmSync(false),
    });
  }

  const isDraftView = statusFilter === "DRAFT";
  const { data, isLoading, error } = useWaTemplates({
    search: debounced || undefined,
    tier: tier === "all" ? undefined : tier,
    // The DRAFT pseudo-status flips include_drafts and clears the
    // backend status filter (drafts have status=null in the DB).
    include_drafts: true,
    status: ["all", "DRAFT"].includes(statusFilter) ? undefined : statusFilter,
  });

  const rows = (data?.templates ?? []).filter((t) => {
    if (statusFilter === "DRAFT") return t.is_draft;
    if (statusFilter === "all") return true;
    return (t.status || "").toUpperCase() === statusFilter;
  });

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-col gap-2 border-b border-border p-card">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
            Templates ({rows.length})
          </h2>
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="outline"
              onClick={() => !syncing && setConfirmSync(true)}
              disabled={!!syncing}
              title="Sync from Meta"
            >
              <RefreshCw className={cn("mr-1 h-4 w-4", syncing && "animate-spin")} />
              {syncing ? "Syncing…" : "Sync"}
            </Button>
            <Button size="sm" onClick={onCreateNew}>
              <Plus className="mr-1 h-4 w-4" /> New draft
            </Button>
          </div>
        </div>
        {syncJob && syncJob.status === "done" && (
          <p className="text-[11px] text-success" role="status">
            {syncJob.message || "Sync complete"}
          </p>
        )}
        {syncJob && syncJob.status === "failed" && (
          <p className="text-[11px] text-danger" role="alert">
            Sync failed: {syncJob.message}
          </p>
        )}
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-text-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name…"
            className="pl-8"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            value={tier}
            onChange={(e) => setTier(e.target.value)}
            className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
          >
            {TIER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      <ul className="flex-1 overflow-auto" role="listbox" aria-label="Templates">
        {isLoading && (
          <li className="p-card text-sm text-text-muted">Loading…</li>
        )}
        {error && (
          <li className="p-card text-sm text-danger" role="alert">
            {error.message}
          </li>
        )}
        {!isLoading && rows.length === 0 && (
          <li className="p-card text-sm text-text-muted">No templates match.</li>
        )}
        {rows.map((t) => (
          <Row
            key={t.id}
            template={t}
            isActive={t.id === selectedId}
            onClick={() => onSelect(t.id)}
            isDraftView={isDraftView}
          />
        ))}
      </ul>

      <ConfirmDialog
        open={confirmSync}
        onOpenChange={setConfirmSync}
        title="Sync templates from Meta?"
        description="Pulls the latest status, category, and components from your WhatsApp Business Account. Drafts are preserved. This calls Meta's API in the background — usually completes in seconds."
        confirmLabel="Sync"
        isPending={syncMutation.isPending}
        onConfirm={performSync}
      />
    </div>
  );
}

function Row({
  template,
  isActive,
  onClick,
}: {
  template: WATemplateOut;
  isActive: boolean;
  onClick: () => void;
  isDraftView: boolean;
}) {
  const status = template.is_draft ? "DRAFT" : (template.status || "PENDING").toUpperCase();
  return (
    <li
      role="option"
      aria-selected={isActive}
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col gap-0.5 border-b border-border/40 px-card py-2 transition-colors",
        "hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        isActive && "bg-card/80",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium text-text">{template.name}</span>
        <StatusPill status={status} />
      </div>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-text-muted">
        <span>{template.tier}</span>
        <span>·</span>
        <span>{template.category || "?"}</span>
        <span>·</span>
        <span>{template.language}</span>
      </div>
    </li>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone = (() => {
    if (status === "APPROVED") return "success";
    if (status === "REJECTED") return "danger";
    if (status === "PENDING") return "warning";
    if (status === "DRAFT") return "muted";
    return "muted";
  })();
  const cls: Record<string, string> = {
    success: "border-success/40 bg-success/10 text-success",
    danger: "border-danger/40 bg-danger/10 text-danger",
    warning: "border-warning/40 bg-warning/10 text-warning",
    muted: "border-border bg-card text-text-muted",
  };
  return (
    <span className={cn("shrink-0 rounded-pill border px-2 py-0.5 text-[9px] font-medium uppercase tracking-wider", cls[tone])}>
      {status}
    </span>
  );
}

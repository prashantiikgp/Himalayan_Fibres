/**
 * <EmailTemplateList> — left panel of /email-templates.
 *
 * Mirrors the WA Templates list shape: search + filters at the top,
 * scrollable list below. Email templates have no Meta-style status —
 * the only status is is_active (active / inactive).
 */

import { useState } from "react";
import { Search, Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { useDebouncedValue } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import {
  useDeleteEmailTemplate,
  useEmailTemplates,
  type EmailTemplateOut,
} from "@/api/email_templates";

export function EmailTemplateList({
  selectedId,
  onSelect,
  onCreateNew,
  onDeleted,
}: {
  selectedId: number | null;
  onSelect: (id: number) => void;
  onCreateNew: () => void;
  onDeleted?: (id: number) => void;
}) {
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("all");
  const [confirmDelete, setConfirmDelete] = useState<EmailTemplateOut | null>(null);
  const debounced = useDebouncedValue(search, 250);
  const deleteMutation = useDeleteEmailTemplate();

  const { data, isLoading, error } = useEmailTemplates({
    search: debounced || undefined,
    active_only: activeFilter === "active",
  });

  const rows = (data?.templates ?? []).filter((t) => {
    if (activeFilter === "inactive") return !t.is_active;
    return true;
  });

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-col gap-2 border-b border-border p-card">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
            Email templates ({rows.length})
          </h2>
          <Button size="sm" onClick={onCreateNew}>
            <Plus className="mr-1 h-4 w-4" /> New
          </Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-text-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or slug…"
            className="pl-8"
          />
        </div>
        <select
          value={activeFilter}
          onChange={(e) => setActiveFilter(e.target.value as typeof activeFilter)}
          className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
        >
          <option value="all">All</option>
          <option value="active">Active only</option>
          <option value="inactive">Inactive only</option>
        </select>
      </header>

      <ul className="flex-1 overflow-auto" role="listbox" aria-label="Email templates">
        {isLoading && <li className="p-card text-sm text-text-muted">Loading…</li>}
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
            onDeleteClick={() => setConfirmDelete(t)}
          />
        ))}
      </ul>

      <ConfirmDialog
        open={confirmDelete !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmDelete(null);
        }}
        title={
          confirmDelete
            ? `Delete "${confirmDelete.name}"?`
            : "Delete template?"
        }
        description={
          "This template will be permanently removed. Broadcasts that already used this slug keep their record (sent history is preserved)."
        }
        confirmLabel="Delete"
        destructive
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (!confirmDelete) return;
          const deletedId = confirmDelete.id;
          deleteMutation.mutate(deletedId, {
            onSuccess: () => {
              setConfirmDelete(null);
              onDeleted?.(deletedId);
            },
            onError: () => {
              setConfirmDelete(null);
            },
          });
        }}
      />
    </div>
  );
}

function Row({
  template,
  isActive,
  onClick,
  onDeleteClick,
}: {
  template: EmailTemplateOut;
  isActive: boolean;
  onClick: () => void;
  onDeleteClick: () => void;
}) {
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
        "group flex cursor-pointer flex-col gap-0.5 border-b border-border/40 px-card py-2 transition-colors",
        "hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        isActive && "bg-card/80",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium text-text">{template.name}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            className={cn(
              "rounded-pill border px-2 py-0.5 text-[9px] font-medium uppercase tracking-wider",
              template.is_active
                ? "border-success/40 bg-success/10 text-success"
                : "border-border bg-card text-text-muted",
            )}
          >
            {template.is_active ? "Active" : "Inactive"}
          </span>
          <button
            type="button"
            aria-label={`Delete template ${template.name}`}
            title="Delete template"
            onClick={(e) => {
              e.stopPropagation();
              onDeleteClick();
            }}
            className="rounded p-1 text-text-muted opacity-0 transition-opacity hover:bg-danger/10 hover:text-danger focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger group-hover:opacity-100"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-text-muted">
        <code>{template.slug}</code>
        <span>·</span>
        <span>{template.email_type}</span>
        {template.category && (
          <>
            <span>·</span>
            <span>{template.category}</span>
          </>
        )}
      </div>
    </li>
  );
}

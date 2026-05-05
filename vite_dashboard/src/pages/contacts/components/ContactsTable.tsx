/**
 * <ContactsTable> — composes <DataTable> with the column defs.
 */

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Pencil } from "lucide-react";
import { DataTable } from "@/components/tables/DataTable";
import { ChannelBadge } from "@/components/badges/ChannelBadge";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ContactRow } from "@/api/contacts";

const MISSING = <span className="italic text-text-muted/80">missing</span>;

export function ContactsTable({
  data,
  isLoading,
  error,
  onEdit,
}: {
  data: ContactRow[];
  isLoading: boolean;
  error: Error | null;
  onEdit?: (contact: ContactRow) => void;
}) {
  const columns = useMemo<ColumnDef<ContactRow, unknown>[]>(
    () => [
      {
        id: "name",
        header: "Name",
        cell: ({ row }) => {
          const c = row.original;
          const name = `${c.first_name} ${c.last_name}`.trim();
          return (
            <div className="font-medium text-text">{name || MISSING}</div>
          );
        },
      },
      {
        id: "company",
        header: "Company",
        cell: ({ row }) => row.original.company || MISSING,
      },
      {
        id: "channels",
        header: "Channels",
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.channels.length === 0
              ? MISSING
              : row.original.channels.map((ch) => <ChannelBadge key={ch} channel={ch} />)}
          </div>
        ),
      },
      {
        id: "lifecycle",
        header: "Lifecycle",
        cell: ({ row }) => (
          <span className={cn("text-xs text-text-subtle")}>{row.original.lifecycle || "—"}</span>
        ),
      },
      {
        id: "consent",
        header: "Consent",
        cell: ({ row }) =>
          row.original.consent_status ? (
            <StatusBadge domain="contact" status={row.original.consent_status} />
          ) : (
            MISSING
          ),
      },
      {
        id: "email",
        header: "Email",
        cell: ({ row }) => (
          <span className="font-mono text-xs text-text-muted">{row.original.email || MISSING}</span>
        ),
      },
      {
        id: "phone",
        header: "Phone",
        cell: ({ row }) => (
          <span className="font-mono text-xs text-text-muted">{row.original.phone || MISSING}</span>
        ),
      },
      {
        id: "tags",
        header: "Tags",
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.tags.slice(0, 3).map((t) => (
              <span
                key={t}
                className="rounded border border-border bg-card px-1.5 py-0.5 text-[10px] text-text-muted"
              >
                {t}
              </span>
            ))}
            {row.original.tags.length > 3 && (
              <span className="text-[10px] text-text-muted">+{row.original.tags.length - 3}</span>
            )}
          </div>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${row.original.first_name || row.original.id}`}
            onClick={(e) => {
              e.stopPropagation();
              onEdit?.(row.original);
            }}
          >
            <Pencil className="h-4 w-4" />
          </Button>
        ),
      },
    ],
    [onEdit],
  );

  return (
    <DataTable
      data={data}
      columns={columns}
      isLoading={isLoading}
      error={error}
      getRowId={(row) => row.id}
      emptyMessage="No contacts match your filters."
      onRowClick={onEdit}
    />
  );
}

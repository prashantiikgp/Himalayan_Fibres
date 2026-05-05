/**
 * <DataTable> — generic TanStack-Table-based data table.
 *
 * Used by Phase 1 Contacts (this commit) and reused by every later phase
 * that lists rows (Broadcasts/History, WA Templates list, Flow runs).
 * Per the audit's "promote to global only when 2+ pages use it" rule, this
 * lives under src/components/tables/.
 *
 * Production-ready: empty / loading / error states, mobile horizontal
 * scroll, accessible row click via button role.
 */

import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { cn } from "@/lib/utils";
import { STRINGS } from "@/lib/strings";

export type DataTableProps<T> = {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  isLoading?: boolean;
  error?: Error | null;
  onRowClick?: (row: T) => void;
  /** Stable string key per row — falls back to row index. */
  getRowId?: (row: T, index: number) => string;
  emptyMessage?: string;
  className?: string;
};

export function DataTable<T>({
  data,
  columns,
  isLoading = false,
  error = null,
  onRowClick,
  getRowId,
  emptyMessage = STRINGS.table.empty,
  className,
}: DataTableProps<T>) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId,
  });

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-card",
        className,
      )}
    >
      <div className="max-h-[calc(100vh-280px)] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 border-b border-border bg-card/95 backdrop-blur">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    scope="col"
                    className="px-card py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted"
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {error && (
              <tr>
                <td colSpan={columns.length} className="px-card py-6 text-center text-danger">
                  {error.message}
                </td>
              </tr>
            )}
            {!error && isLoading && data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-card py-8 text-center text-text-muted">
                  {STRINGS.table.loading}
                </td>
              </tr>
            )}
            {!error && !isLoading && data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-card py-8 text-center text-text-muted">
                  {emptyMessage}
                </td>
              </tr>
            )}
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={cn(
                  "border-b border-border/40 transition-colors last:border-0",
                  onRowClick && "cursor-pointer hover:bg-card/60",
                )}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(row.original);
                        }
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? "button" : undefined}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-card py-2 align-middle">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

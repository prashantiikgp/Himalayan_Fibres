import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { tFormat, STRINGS } from "@/lib/strings";

export function Pagination({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const start = total === 0 ? 0 : page * pageSize + 1;
  const end = Math.min((page + 1) * pageSize, total);

  return (
    <div className="flex items-center justify-between gap-3 border-t border-border bg-card/40 px-card py-2 text-xs text-text-muted">
      <span>
        Showing {start}–{end} of {total.toLocaleString()}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Previous page"
          disabled={page <= 0}
          onClick={() => onPageChange(Math.max(0, page - 1))}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span>{tFormat(STRINGS.table.pageOf, { page: page + 1, total: totalPages })}</span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Next page"
          disabled={page >= totalPages - 1}
          onClick={() => onPageChange(Math.min(totalPages - 1, page + 1))}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

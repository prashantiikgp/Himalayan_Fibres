/**
 * Contacts page — Phase 1.
 *
 * Ships in this commit: list + filter + paginate + URL state.
 * Drawer (edit/notes/activity), Add dialog, Import, CSV download — follow-up.
 *
 * Per STANDARDS production-readiness principle: no placeholders. Every
 * column renders real data; filters apply through to the API; URL state
 * survives reload.
 *
 * Bug fixes shipped: B19 (URL routing — every filter/page in the URL).
 */

import { useState, useMemo, useDeferredValue } from "react";
import { useContacts } from "@/api/contacts";
import { pageEngine } from "@/engines/pageEngine";
import { useUrlState } from "@/lib/url-state";
import { ContactsTable } from "./components/ContactsTable";
import { ContactsFilterBar, DEFAULT_FILTERS, type ContactFilters } from "./components/ContactsFilterBar";
import { Pagination } from "@/components/tables/Pagination";

export function ContactsPage() {
  const meta = pageEngine.getMeta("contacts");
  const cfg = pageEngine.getConfig("contacts");
  const url = useUrlState();

  const filters: ContactFilters = useMemo(
    () => ({
      segment: url.get("segment", DEFAULT_FILTERS.segment),
      lifecycle: url.get("lifecycle", DEFAULT_FILTERS.lifecycle),
      country: url.get("country", DEFAULT_FILTERS.country),
      channel: (url.get("channel", DEFAULT_FILTERS.channel) as ContactFilters["channel"]) ?? "all",
      search: url.get("search", ""),
    }),
    [url],
  );

  const [page, setPage] = useState(() => Math.max(0, parseInt(url.get("page", "0"), 10) || 0));

  const handleFilterChange = (next: Partial<ContactFilters>) => {
    url.set({ ...next, page: null });
    setPage(0);
  };

  const handlePageChange = (nextPage: number) => {
    setPage(nextPage);
    url.set({ page: nextPage > 0 ? String(nextPage) : null });
  };

  // Debounce-lite: defer search-driven refetches by one paint
  // so typing isn't laggy. TanStack Query's keepPreviousData smooths the rest.
  const deferredFilters = useDeferredValue(filters);

  const { data, isLoading, error } = useContacts({
    segment: deferredFilters.segment,
    lifecycle: deferredFilters.lifecycle,
    country: deferredFilters.country,
    channel: deferredFilters.channel,
    search: deferredFilters.search,
    page,
    page_size: cfg.page.table.page_size,
  });

  return (
    <div className="flex flex-col gap-section" style={pageEngine.getStyleVars("contacts")}>
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-text">{meta.title}</h1>
        <p className="text-sm text-text-muted">{meta.subtitle}</p>
      </header>

      <div className="flex flex-col gap-section md:flex-row">
        <ContactsFilterBar value={filters} onChange={handleFilterChange} />

        <div className="min-w-0 flex-1 flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span>
              {data ? `${data.total.toLocaleString()} contacts` : "Loading contacts…"}
            </span>
          </div>

          <ContactsTable
            data={data?.contacts ?? []}
            isLoading={isLoading}
            error={error instanceof Error ? error : null}
          />

          {data && data.total > 0 && (
            <Pagination
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              totalPages={data.total_pages}
              onPageChange={handlePageChange}
            />
          )}
        </div>
      </div>
    </div>
  );
}

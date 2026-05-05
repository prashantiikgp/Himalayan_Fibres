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

import { useState, useMemo } from "react";
import { Download } from "lucide-react";
import { useContacts, type ContactRow } from "@/api/contacts";
import { pageEngine } from "@/engines/pageEngine";
import { useUrlState } from "@/lib/url-state";
import { useDebouncedValue } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { ContactsTable } from "./components/ContactsTable";
import { ContactsFilterBar, DEFAULT_FILTERS, type ContactFilters } from "./components/ContactsFilterBar";
import { ContactDrawer } from "./components/ContactDrawer";
import { AddContactDialog } from "./components/AddContactDialog";
import { ImportContactsDialog } from "./components/ImportContactsDialog";
import { Pagination } from "@/components/tables/Pagination";
import { apiBase } from "@/lib/env";
import { getToken } from "@/lib/auth";

async function downloadContactsCsv() {
  const token = getToken();
  const res = await fetch(`${apiBase()}/api/v2/contacts.csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    alert(`CSV download failed: ${res.status}`);
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "contacts.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

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
  const [drawerContact, setDrawerContact] = useState<ContactRow | null>(null);

  const handleFilterChange = (next: Partial<ContactFilters>) => {
    url.set({ ...next, page: null });
    setPage(0);
  };

  const handlePageChange = (nextPage: number) => {
    setPage(nextPage);
    url.set({ page: nextPage > 0 ? String(nextPage) : null });
  };

  // Debounce the search field by 300ms so each keystroke doesn't fire a
  // request (review fix M5). Other filters (select dropdowns) update on
  // discrete change events and don't need debouncing.
  const debouncedSearch = useDebouncedValue(filters.search, 300);

  const { data, isLoading, error } = useContacts({
    segment: filters.segment,
    lifecycle: filters.lifecycle,
    country: filters.country,
    channel: filters.channel,
    search: debouncedSearch,
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
          <div className="flex items-center justify-between gap-2 text-xs text-text-muted">
            <span>
              {data ? `${data.total.toLocaleString()} contacts` : "Loading contacts…"}
            </span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={downloadContactsCsv}>
                <Download className="mr-1 h-4 w-4" /> CSV
              </Button>
              <ImportContactsDialog />
              <AddContactDialog />
            </div>
          </div>

          <ContactsTable
            data={data?.contacts ?? []}
            isLoading={isLoading}
            error={error instanceof Error ? error : null}
            onEdit={setDrawerContact}
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

      <ContactDrawer
        contact={drawerContact}
        open={drawerContact !== null}
        onOpenChange={(open) => {
          if (!open) setDrawerContact(null);
        }}
      />
    </div>
  );
}

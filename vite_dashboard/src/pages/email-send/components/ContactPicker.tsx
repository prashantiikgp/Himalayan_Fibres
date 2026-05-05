/**
 * <ContactPicker> — search-as-you-type list of contacts that have an email.
 *
 * Mirrors WA Inbox's ConversationList shape: search input on top, scrolling
 * result list below. Filtered server-side to contacts on the email channel.
 * Selecting one bubbles the contact up; the parent shows the full Contact card.
 *
 * Phase 7.1 (Day_4_improvememt/PLAN_email.md).
 */

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useContacts, type ContactRow } from "@/api/contacts";
import { useDebouncedValue } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export function ContactPicker({
  selected,
  onSelect,
  onClear,
}: {
  selected: ContactRow | null;
  onSelect: (c: ContactRow) => void;
  onClear: () => void;
}) {
  const [search, setSearch] = useState("");
  const [pickerOpen, setPickerOpen] = useState(selected === null);
  const debounced = useDebouncedValue(search, 250);

  // Auto-collapse the search list when a contact is picked, auto-expand
  // when the founder clicks Clear (selected → null).
  useEffect(() => {
    setPickerOpen(selected === null);
  }, [selected]);

  const { data, isLoading, error } = useContacts({
    search: debounced || undefined,
    channel: "email",
    page_size: 25,
  });

  // Defensive: backend already filters by channel, but make sure rows
  // without an email never appear (a contact may be on email channel
  // by intent without yet having a verified address).
  const rows = (data?.contacts ?? []).filter((c) => (c.email || "").trim().length > 0);

  return (
    <div className="flex flex-col gap-2">
      {selected && (
        <div
          aria-label="Selected contact"
          className="flex items-start justify-between gap-2 rounded-md border border-primary/30 bg-primary/5 p-2 text-sm"
        >
          <div className="min-w-0 flex-1">
            <div className="truncate font-semibold text-text">
              {[selected.first_name, selected.last_name].filter(Boolean).join(" ") ||
                selected.email}
            </div>
            <div className="truncate text-xs text-text-muted">{selected.email}</div>
            {selected.company && (
              <div className="truncate text-xs text-text-muted">{selected.company}</div>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <button
              type="button"
              onClick={() => setPickerOpen((v) => !v)}
              className="text-xs text-primary hover:underline"
            >
              {pickerOpen ? "Hide list" : "Change"}
            </button>
            <button
              type="button"
              onClick={onClear}
              className="text-xs text-text-muted hover:text-danger"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {pickerOpen && (
        <>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-text-muted" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, email, company"
              className="pl-8"
              aria-label="Search contacts"
            />
          </div>

          <ul
            role="listbox"
            aria-label="Contacts with email"
            className="max-h-72 overflow-auto rounded-md border border-border"
          >
            {isLoading && (
              <li className="p-2 text-xs text-text-muted">Searching…</li>
            )}
            {error && (
              <li className="p-2 text-xs text-danger" role="alert">
                {error.message}
              </li>
            )}
            {!isLoading && rows.length === 0 && (
              <li className="p-2 text-xs text-text-muted">
                {debounced
                  ? "No contacts match your search."
                  : "Start typing to find a contact."}
              </li>
            )}
            {rows.map((c) => {
              const isActive = selected?.id === c.id;
              const display =
                [c.first_name, c.last_name].filter(Boolean).join(" ") || c.email;
              return (
                <li key={c.id} role="option" aria-selected={isActive}>
                  <button
                    type="button"
                    onClick={() => onSelect(c)}
                    className={cn(
                      "flex w-full flex-col items-start gap-0 px-2 py-1.5 text-left text-sm transition-colors",
                      isActive
                        ? "bg-primary/10 text-text"
                        : "text-text hover:bg-card",
                    )}
                  >
                    <span className="truncate font-medium">{display}</span>
                    <span className="truncate text-xs text-text-muted">{c.email}</span>
                    {c.company && (
                      <span className="truncate text-xs text-text-muted">{c.company}</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}

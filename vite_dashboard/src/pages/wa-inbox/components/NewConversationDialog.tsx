/**
 * <NewConversationDialog> — Sheet-based picker for starting a WA
 * conversation with a contact who has no WAChat row yet.
 *
 * The send pipeline (`POST /api/v2/wa/template-sends` →
 * `_ensure_chat`) creates the WAChat on first template send, so this
 * component is purely a navigation step: it sets `?contact=<id>` so
 * ChatPanel renders the empty-state ClosedWindowCta and the operator
 * can hit "Send a template".
 *
 * Cache dependency (per plan §7.6 cache-invalidation note): the
 * "Hide existing conversations" toggle reads from the same
 * `["wa","conversations"]` query key that `useSendTemplate`
 * invalidates, so the picker self-refreshes after a send (AC-7.6.5).
 */

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { useContacts, type ContactRow } from "@/api/contacts";
import { useConversations } from "@/api/wa";
import { useDebouncedValue } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Labels = {
  title: string;
  help: string;
  hide_existing_label: string;
  search_placeholder: string;
};

export function NewConversationDialog({
  open,
  onOpenChange,
  onPick,
  labels,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `displayName` is the picker's best-effort name so WAInboxPage can
   * fall back to it when the conversations list lookup misses (the
   * picked contact has no WAChat row yet). */
  onPick: (contactId: string, displayName: string) => void;
  labels: Labels;
}) {
  const [search, setSearch] = useState("");
  const debounced = useDebouncedValue(search, 250);
  const [hideExisting, setHideExisting] = useState(true);

  const { data, isLoading, error } = useContacts({
    channel: "whatsapp",
    search: debounced || undefined,
    page_size: 50,
  });

  // Reads the same query key useSendTemplate invalidates — picker
  // self-refreshes after a send. Bumped to 200 to cover the inbox
  // scale; if more conversations exist, exclusion may miss a few but
  // that's a safe degradation (just shows a row that's already a chat).
  const { data: convData } = useConversations({ page_size: 200 });
  const existingContactIds = useMemo(() => {
    const set = new Set<string>();
    for (const c of convData?.conversations ?? []) set.add(c.contact_id);
    return set;
  }, [convData]);

  const filtered = useMemo(() => {
    const rows = data?.contacts ?? [];
    if (!hideExisting) return rows;
    return rows.filter((r) => !existingContactIds.has(r.id));
  }, [data, hideExisting, existingContactIds]);

  function handlePick(contact: ContactRow) {
    const fullName = [contact.first_name, contact.last_name]
      .filter(Boolean)
      .join(" ")
      .trim();
    const displayName = fullName || contact.company || contact.id;
    onPick(contact.id, displayName);
    onOpenChange(false);
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{labels.title}</SheetTitle>
          <SheetDescription>{labels.help}</SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-3 overflow-hidden px-card pb-card">
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-text-muted" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={labels.search_placeholder}
              className="pl-8"
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={hideExisting}
              onChange={(e) => setHideExisting(e.target.checked)}
              className="h-3.5 w-3.5"
            />
            {labels.hide_existing_label}
          </label>

          <ul
            role="listbox"
            aria-label="Contacts with WhatsApp"
            className="flex-1 overflow-auto rounded-md border border-border bg-card/40"
          >
            {isLoading && (
              <li className="p-card text-sm text-text-muted">Loading contacts…</li>
            )}
            {error && (
              <li className="p-card text-sm text-danger" role="alert">
                {error.message}
              </li>
            )}
            {!isLoading && !error && filtered.length === 0 && (
              <li className="p-card text-sm text-text-muted">
                No matching contacts. Try clearing the search or unchecking
                "{labels.hide_existing_label}".
              </li>
            )}
            {filtered.map((c) => (
              <ContactPickerRow
                key={c.id}
                contact={c}
                onPick={() => handlePick(c)}
                hasExistingConversation={existingContactIds.has(c.id)}
              />
            ))}
          </ul>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ContactPickerRow({
  contact,
  onPick,
  hasExistingConversation,
}: {
  contact: ContactRow;
  onPick: () => void;
  hasExistingConversation: boolean;
}) {
  const fullName = [contact.first_name, contact.last_name]
    .filter(Boolean)
    .join(" ")
    .trim() || "(no name)";
  const consent = (contact.consent_status || "").toLowerCase();
  // (b) "warn only" per plan D7 — never block selection at picker level.
  // Phase 8 ships the proper send-side gating.
  const consentWarn = consent === "opt_out";

  return (
    <li
      role="option"
      aria-selected="false"
      tabIndex={0}
      onClick={onPick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onPick();
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col gap-0.5 border-b border-border/40 px-card py-2 transition-colors",
        "hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium text-text">
          {fullName}
          {contact.company && (
            <span className="ml-1 text-text-muted">· {contact.company}</span>
          )}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          {hasExistingConversation && (
            <span
              className="rounded-pill bg-card px-1.5 py-0.5 text-[10px] text-text-muted"
              title="Already has a conversation"
            >
              existing
            </span>
          )}
          {consentWarn && (
            <span
              className="rounded-pill bg-warning/20 px-1.5 py-0.5 text-[10px] text-warning"
              title="Customer opted out — send may be rejected"
            >
              opted out
            </span>
          )}
        </div>
      </div>
      <span className="truncate text-xs text-text-subtle">
        {contact.phone || contact.wa_id || "—"}
      </span>
    </li>
  );
}

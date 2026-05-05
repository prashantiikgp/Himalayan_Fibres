/**
 * <ConversationList> — left panel of the WA Inbox.
 *
 * Lists active conversations with last-message preview, relative time,
 * unread count, and window-open indicator. Selecting a row sets the
 * active conversation in the parent.
 */

import { useRef, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useConversations, type ConversationListItem } from "@/api/wa";
import { useDebouncedValue } from "@/lib/hooks";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ConversationList({
  selectedContactId,
  onSelect,
  searchPlaceholder,
  onNewConversation,
  newConversationLabel,
}: {
  selectedContactId: string | null;
  onSelect: (contactId: string) => void;
  searchPlaceholder: string;
  onNewConversation?: () => void;
  newConversationLabel?: string;
}) {
  const [search, setSearch] = useState("");
  const debounced = useDebouncedValue(search, 250);
  // Phase 2.0 always shows page 0; pagination UI lands when the inbox
  // accumulates enough chats to need it.
  const { data, isLoading, error } = useConversations({
    search: debounced || undefined,
    page_size: 100,
  });
  const listRef = useRef<HTMLUListElement>(null);

  // Keyboard navigation per WAI-ARIA listbox role (review fix #10):
  // ArrowUp/Down move focus + selection within the list, Home/End jump
  // to ends. Enter/Space on a row activates it (handled per-row).
  function handleListKeyDown(e: React.KeyboardEvent<HTMLUListElement>) {
    if (!data) return;
    const total = data.conversations.length;
    if (total === 0) return;
    const currentIdx = data.conversations.findIndex(
      (c) => c.contact_id === selectedContactId,
    );

    let nextIdx: number | null = null;
    if (e.key === "ArrowDown") nextIdx = Math.min(total - 1, (currentIdx < 0 ? -1 : currentIdx) + 1);
    else if (e.key === "ArrowUp") nextIdx = Math.max(0, (currentIdx < 0 ? total : currentIdx) - 1);
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = total - 1;
    if (nextIdx === null) return;

    const next = data.conversations[nextIdx];
    if (!next) return;
    e.preventDefault();
    onSelect(next.contact_id);
    // Move DOM focus to the newly-selected row so the ring follows it.
    const rows = listRef.current?.querySelectorAll<HTMLLIElement>('[role="option"]');
    rows?.[nextIdx]?.focus();
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-card">
        {onNewConversation && (
          <button
            type="button"
            onClick={onNewConversation}
            className="mb-2 w-full rounded-md border border-border bg-card px-2 py-1.5 text-xs font-medium text-text hover:bg-card/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {newConversationLabel ?? "+ New conversation"}
          </button>
        )}
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-text-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={searchPlaceholder}
            className="pl-8"
          />
        </div>
      </div>
      <ul
        ref={listRef}
        className="flex-1 overflow-auto"
        role="listbox"
        aria-label="Conversations"
        tabIndex={data && data.conversations.length > 0 ? 0 : -1}
        onKeyDown={handleListKeyDown}
      >
        {isLoading && (
          <li className="p-card text-sm text-text-muted">Loading conversations…</li>
        )}
        {error && (
          <li className="p-card text-sm text-danger" role="alert">
            {error.message}
          </li>
        )}
        {data && data.conversations.length === 0 && (
          <li className="p-card text-sm text-text-muted">No active conversations.</li>
        )}
        {data?.conversations.map((c) => (
          <ConversationRow
            key={c.contact_id}
            item={c}
            isActive={c.contact_id === selectedContactId}
            onClick={() => onSelect(c.contact_id)}
          />
        ))}
      </ul>
    </div>
  );
}

function ConversationRow({
  item,
  isActive,
  onClick,
}: {
  item: ConversationListItem;
  isActive: boolean;
  onClick: () => void;
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
        "flex cursor-pointer flex-col gap-0.5 border-b border-border/40 px-card py-2 transition-colors",
        "hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        isActive && "bg-card/80",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium text-text">
          {item.contact_name}
        </span>
        {item.last_message_at && (
          <span className="shrink-0 text-[10px] text-text-muted">
            {formatRelative(item.last_message_at)}
          </span>
        )}
      </div>
      {item.contact_company && (
        <span className="truncate text-xs text-text-muted">{item.contact_company}</span>
      )}
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs text-text-subtle">
          {item.last_message_preview || "—"}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          {item.window_open && (
            <span
              className="inline-block h-2 w-2 rounded-full bg-success"
              title="24h window open"
              aria-label="Window open"
            />
          )}
          {item.unread_count > 0 && (
            <span className="rounded-pill bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-white">
              {item.unread_count}
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

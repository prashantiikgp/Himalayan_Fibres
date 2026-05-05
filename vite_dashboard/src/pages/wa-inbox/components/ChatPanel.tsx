/**
 * <ChatPanel> — center panel of the WA Inbox.
 *
 * Shows the conversation header, message list, and the composer. When
 * the 24h customer-service window is closed (or no inbound has ever
 * been received), the composer is replaced with a contextual CTA —
 * this is the B2 fix.
 */

import { useEffect, useRef } from "react";
import { useConversationDetail } from "@/api/wa";
import { formatRelative } from "@/lib/format";
import { MessageBubble } from "./MessageBubble";

type Labels = {
  compose_placeholder: string;
  window_warning: string;
  new_conv_warning: string;
};

export function ChatPanel({
  selectedContactId,
  labels,
  onOpenTemplateSheet,
}: {
  selectedContactId: string | null;
  labels: Labels;
  /** Callback to surface the Send-Template sheet (Phase 2.1+). */
  onOpenTemplateSheet: () => void;
}) {
  const { data, isLoading, error } = useConversationDetail(selectedContactId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messageContainerRef = useRef<HTMLDivElement>(null);
  const previousLengthRef = useRef(0);

  // Auto-scroll only when (a) a NEW message arrives AND (b) the user is
  // already near the bottom — so reading older messages isn't disrupted
  // by the 15s refetch (review fix #7).
  useEffect(() => {
    const length = data?.messages.length ?? 0;
    const grew = length > previousLengthRef.current;
    previousLengthRef.current = length;
    if (!grew) return;
    const el = messageContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 120) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [data?.messages.length]);

  // Reset the previous-length tracker when switching conversations so a
  // fresh chat doesn't suppress the initial scroll.
  useEffect(() => {
    previousLengthRef.current = 0;
  }, [selectedContactId]);

  if (selectedContactId === null) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">
        Select a conversation
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">
        Loading conversation…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-full items-center justify-center px-card text-sm text-danger" role="alert">
        {error?.message ?? "Conversation not found"}
      </div>
    );
  }

  const hasInbound = data.last_inbound_at !== null;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border px-card py-2">
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-text">{data.contact_name}</span>
          <span className="text-xs text-text-muted">
            {data.contact_company || data.contact_phone}
          </span>
        </div>
        {/* Review fix #13: dropped the ChannelBadge — every chat here is */}
        {/* WhatsApp by construction so the badge was visual noise. */}
        <div className="flex items-center gap-2 text-xs">
          {data.window_open ? (
            <span
              className="rounded-pill border border-success/40 bg-success/10 px-2 py-0.5 text-success"
              title={`Window open until ${data.window_expires_at ?? "—"}`}
            >
              Window open
            </span>
          ) : (
            <span className="rounded-pill border border-warning/40 bg-warning/10 px-2 py-0.5 text-warning">
              Window closed
            </span>
          )}
        </div>
      </header>

      <div ref={messageContainerRef} className="flex-1 overflow-auto px-card py-3">
        <ul className="flex flex-col gap-2">
          {data.messages.length === 0 && (
            <li className="text-center text-xs text-text-muted">
              No messages yet.
            </li>
          )}
          {data.messages.map((m) => (
            <li key={m.id}>
              <MessageBubble message={m} />
            </li>
          ))}
        </ul>
        <div ref={messagesEndRef} />
        {data.last_inbound_at && (
          <p className="mt-3 text-center text-[10px] text-text-muted">
            Last inbound: {formatRelative(data.last_inbound_at)}
          </p>
        )}
      </div>

      {data.window_open && hasInbound ? (
        // Review fix #6: instead of greyed-out Send/Attach that look
        // broken, show a single placeholder banner. The real composer
        // wires up in Phase 2.1.
        <ComposerPlaceholder placeholder={labels.compose_placeholder} />
      ) : (
        <ClosedWindowCta
          warning={hasInbound ? labels.window_warning : labels.new_conv_warning}
          onOpenTemplateSheet={onOpenTemplateSheet}
        />
      )}
    </div>
  );
}

function ComposerPlaceholder({ placeholder }: { placeholder: string }) {
  return (
    <div className="border-t border-border bg-card/40 px-card py-3">
      <p className="text-xs text-text-muted">
        Reply composer ({placeholder.toLowerCase()}) lands in Phase 2.1.
      </p>
    </div>
  );
}

function ClosedWindowCta({
  warning,
  onOpenTemplateSheet,
}: {
  warning: string;
  onOpenTemplateSheet: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 border-t border-warning/40 bg-warning/5 px-card py-3">
      <p className="text-sm text-warning">{warning}</p>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onOpenTemplateSheet}
          className="rounded-md border border-border bg-card px-3 py-1 text-xs font-medium text-text hover:bg-card/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          Send a template
        </button>
      </div>
    </div>
  );
}

// Composer + Composer-state useState removed — Phase 2.1 reintroduces
// them with a working Send button.

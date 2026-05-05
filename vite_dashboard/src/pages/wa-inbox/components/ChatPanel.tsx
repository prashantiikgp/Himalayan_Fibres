/**
 * <ChatPanel> — center panel of the WA Inbox.
 *
 * Shows the conversation header, message list, and the composer. When
 * the 24h customer-service window is closed (or no inbound has ever
 * been received), the composer is replaced with a contextual CTA —
 * this is the B2 fix.
 */

import { useEffect, useRef, useState } from "react";
import { Send, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChannelBadge } from "@/components/badges/ChannelBadge";
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

  // Auto-scroll to the latest message whenever a new one arrives.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [data?.messages.length]);

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
        <div className="flex items-center gap-2 text-xs">
          <ChannelBadge channel="whatsapp" />
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

      <div className="flex-1 overflow-auto px-card py-3">
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
        <Composer placeholder={labels.compose_placeholder} contactId={data.contact_id} />
      ) : (
        <ClosedWindowCta
          warning={hasInbound ? labels.window_warning : labels.new_conv_warning}
          onOpenTemplateSheet={onOpenTemplateSheet}
        />
      )}
    </div>
  );
}

function Composer({
  placeholder,
  contactId,
}: {
  placeholder: string;
  contactId: string;
}) {
  const [text, setText] = useState("");

  // Send wiring lands in Phase 2.1 — for now the composer is functional
  // but the Send button is disabled to avoid pretending to send.
  void contactId;
  const canSend = text.trim().length > 0;

  return (
    <div className="border-t border-border px-card py-2">
      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          rows={1}
          className="min-h-[36px] flex-1 resize-none rounded-md border border-border bg-card p-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        />
        <Button type="button" variant="outline" size="sm" disabled aria-label="Attach">
          <Paperclip className="h-4 w-4" />
        </Button>
        <Button type="button" size="sm" disabled={!canSend} aria-label="Send">
          <Send className="h-4 w-4" />
        </Button>
      </div>
      <p className="mt-1 text-[10px] text-text-muted">
        Send wiring lands in Phase 2.1.
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
        <Button type="button" size="sm" variant="outline" onClick={onOpenTemplateSheet}>
          Send a template
        </Button>
      </div>
    </div>
  );
}

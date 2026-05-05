/**
 * <WAInboxPage> — entry component for /wa-inbox.
 *
 * Phase 2.0 (this commit) ships read-only: list conversations, view a
 * conversation's messages, see window-open state. Send-text and Send-
 * template paths land in Phase 2.1, SSE for live inbound in Phase 2.2.
 *
 * Bug fixes already wired by construction:
 *  - B2 (composer enabled when sending impossible): the composer is
 *    only rendered when window_open AND last_inbound_at exist; otherwise
 *    we render the closed-window CTA.
 */

import { useState } from "react";
import { configLoader } from "@/loaders/configLoader";
import { useSearchParams } from "react-router-dom";
import { ConversationList } from "./components/ConversationList";
import { ChatPanel } from "./components/ChatPanel";

export function WAInboxPage() {
  const cfg = configLoader.getPage("wa_inbox");
  const [params, setParams] = useSearchParams();
  const selected = params.get("contact");
  const [templateSheetOpen, setTemplateSheetOpen] = useState(false);

  function selectContact(contactId: string) {
    const next = new URLSearchParams(params);
    next.set("contact", contactId);
    setParams(next, { replace: true });
  }

  return (
    <div className="grid h-[calc(100vh-var(--shell-topbar-height,56px))] grid-cols-[minmax(240px,1fr)_minmax(380px,2fr)_minmax(320px,2fr)] gap-2 p-2">
      <section
        aria-label="Conversations"
        className="overflow-hidden rounded-lg border border-border bg-card/40"
      >
        <ConversationList
          selectedContactId={selected}
          onSelect={selectContact}
          searchPlaceholder={cfg.page.panels.conversations.search_placeholder}
        />
      </section>

      <section
        aria-label="Chat"
        className="overflow-hidden rounded-lg border border-border bg-card/40"
      >
        <ChatPanel
          selectedContactId={selected}
          labels={cfg.page.panels.chat}
          onOpenTemplateSheet={() => setTemplateSheetOpen(true)}
        />
      </section>

      <section
        aria-label="Tools"
        className="overflow-hidden rounded-lg border border-border bg-card/40 p-card"
      >
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wider text-text-muted">
          {cfg.page.panels.template_sheet.title}
        </h2>
        <p className="text-xs text-text-muted">
          {templateSheetOpen
            ? "Template editor lands in Phase 2.1. The composer-disabled + closed-window CTA already work."
            : "Click 'Send a template' from the chat panel to compose. Wired in Phase 2.1."}
        </p>
      </section>
    </div>
  );
}

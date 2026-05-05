/**
 * <WAInboxPage> — entry component for /wa-inbox.
 *
 * Phase 2.0 shipped read-only (list, detail, window state).
 * Phase 2.1 (this commit) adds the real Composer + TemplateSheet wired
 * to the POST /wa/messages and POST /wa/template-sends mutations.
 *
 * Bug fixes wired by construction:
 *  - B2 (composer enabled when sending impossible): the composer is
 *    only rendered when window_open AND last_inbound_at exist; the
 *    closed-window CTA opens the TemplateSheet instead.
 *  - B1 (variables form scrolling/8 always-visible slots): TemplateSheet
 *    renders exactly N inputs in a non-scrolling vertical stack.
 */

import { useState } from "react";
import { configLoader } from "@/loaders/configLoader";
import { useSearchParams } from "react-router-dom";
import { HowToUse } from "@/components/layout/HowToUse";
import { useConversations, useWaLiveStream } from "@/api/wa";
import { ConversationList } from "./components/ConversationList";
import { ChatPanel } from "./components/ChatPanel";
import { TemplateSheet } from "./components/TemplateSheet";

export function WAInboxPage() {
  const cfg = configLoader.getPage("wa_inbox");
  // Phase 2.2: subscribe to the SSE live stream while this page is
  // mounted. Effect-only — invalidates query keys on inbound events.
  useWaLiveStream();
  const [params, setParams] = useSearchParams();
  const selected = params.get("contact");
  const [templateSheetOpen, setTemplateSheetOpen] = useState(false);

  // Look up the selected contact's display name from the conversation
  // list (cheap — the list query is already in the cache from the left
  // panel) so the TemplateSheet header reads "Sending to <name>".
  const { data: convList } = useConversations({ page_size: 200 });
  const selectedName = selected
    ? convList?.conversations.find((c) => c.contact_id === selected)?.contact_name ?? selected
    : "";

  function selectContact(contactId: string) {
    const next = new URLSearchParams(params);
    next.set("contact", contactId);
    setParams(next, { replace: true });
  }

  // Review fix #12: previously used a CSS var (--shell-topbar-height)
  // that no engine emitted. AppShell topbar is fixed at 56px (h-14).
  // Phase 6.5: HowToUse accordion sits above the 3-panel grid, ~40px
  // when collapsed. Subtracting 96 (56 topbar + 40 accordion) keeps
  // the panels filling the remaining viewport.
  return (
    <div className="flex flex-col">
      <HowToUse pageTitle={cfg.page.title} howTo={cfg.page.how_to_use} />
      <div className="grid h-[calc(100vh-96px)] grid-cols-[minmax(240px,1fr)_minmax(380px,2fr)_minmax(320px,2fr)] gap-2 p-2">
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
        className="flex flex-col overflow-hidden rounded-lg border border-border bg-card/40 p-card"
      >
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-text-muted">
          {cfg.page.panels.template_sheet.title}
        </h2>
        <p className="text-xs text-text-muted">
          Templates work outside the 24h window. Use the chat panel's
          "Send a template" button (or the button below) when the window
          is closed or you're starting a fresh conversation.
        </p>
        <button
          type="button"
          onClick={() => setTemplateSheetOpen(true)}
          disabled={!selected}
          className="mt-3 self-start rounded-md border border-border bg-card px-3 py-1 text-xs font-medium text-text hover:bg-card/80 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          Open template picker
        </button>
      </section>

      <TemplateSheet
        open={templateSheetOpen}
        onOpenChange={setTemplateSheetOpen}
        contactId={selected}
        contactName={selectedName}
        labels={cfg.page.panels.template_sheet}
      />
      </div>
    </div>
  );
}

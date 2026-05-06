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
import { useContactDetail } from "@/api/contacts";
import { ConversationList } from "./components/ConversationList";
import { ChatPanel } from "./components/ChatPanel";
import { TemplateSheet } from "./components/TemplateSheet";
import { NewConversationDialog } from "./components/NewConversationDialog";

export function WAInboxPage() {
  const cfg = configLoader.getPage("wa_inbox");
  // Phase 2.2: subscribe to the SSE live stream while this page is
  // mounted. Effect-only — invalidates query keys on inbound events.
  useWaLiveStream();
  const [params, setParams] = useSearchParams();
  const selected = params.get("contact");
  const [templateSheetOpen, setTemplateSheetOpen] = useState(false);
  const [newConvOpen, setNewConvOpen] = useState(false);
  // Names supplied by the new-conversation picker for contacts that
  // don't yet appear in the conversations list. Keyed by contact_id so
  // multiple successive picks each land with the right header label.
  const [pickedNames, setPickedNames] = useState<Record<string, string>>({});

  // Look up the selected contact's display name from the conversation
  // list (cheap — the list query is already in the cache from the left
  // panel) so the TemplateSheet header reads "Sending to <name>". Falls
  // back to the picker's name (no WAChat row yet) then to the contacts
  // endpoint for direct-URL nav (Phase 9.3) and finally the id.
  const { data: convList } = useConversations({ page_size: 200 });
  const inConvList = !!convList?.conversations.find(
    (c) => c.contact_id === selected,
  );
  const inPickedNames = !!(selected && pickedNames[selected]);
  const { data: contactDetail } = useContactDetail(
    selected && !inConvList && !inPickedNames ? selected : null,
  );
  const fetchedFullName = contactDetail
    ? [contactDetail.first_name, contactDetail.last_name]
        .filter(Boolean)
        .join(" ")
        .trim() || contactDetail.company || ""
    : "";
  const selectedName = selected
    ? convList?.conversations.find((c) => c.contact_id === selected)?.contact_name
      ?? pickedNames[selected]
      ?? fetchedFullName
      ?? selected
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
      {/* Phase 8.5: dropped the third "Tools" column. The chat panel
          already exposes "Send a template" via its CTA, and the
          new-conversation picker (D9) auto-opens TemplateSheet — so
          a third panel was duplicate UI. Grid is now 2-col with the
          chat panel filling the recovered space. */}
      <div className="grid h-[calc(100vh-96px)] grid-cols-[minmax(240px,1fr)_minmax(560px,4fr)] gap-2 p-2">
      <section
        aria-label="Conversations"
        className="overflow-hidden rounded-lg border border-border bg-card/40"
      >
        <ConversationList
          selectedContactId={selected}
          onSelect={selectContact}
          searchPlaceholder={cfg.page.panels.conversations.search_placeholder}
          onNewConversation={() => setNewConvOpen(true)}
          newConversationLabel={cfg.page.panels.conversations.new_conversation_button}
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

      <TemplateSheet
        open={templateSheetOpen}
        onOpenChange={setTemplateSheetOpen}
        contactId={selected}
        contactName={selectedName}
        labels={cfg.page.panels.template_sheet}
      />

      <NewConversationDialog
        open={newConvOpen}
        onOpenChange={setNewConvOpen}
        onPick={(contactId, displayName) => {
          // D9: auto-open TemplateSheet — the only useful next action
          // for a brand-new conversation is sending a template. Stash
          // the name so the sheet header reads "Sending to <name>"
          // before any conversation row exists for this contact.
          setPickedNames((prev) => ({ ...prev, [contactId]: displayName }));
          selectContact(contactId);
          setTemplateSheetOpen(true);
        }}
        labels={{
          title: cfg.page.panels.conversations.new_conversation_dialog_title,
          help: cfg.page.panels.conversations.new_conversation_dialog_help,
          hide_existing_label: cfg.page.panels.conversations.new_conversation_hide_existing_label,
          search_placeholder: cfg.page.panels.conversations.search_placeholder,
        }}
      />
      </div>
    </div>
  );
}

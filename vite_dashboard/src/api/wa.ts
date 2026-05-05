/**
 * /api/v2/wa/* hooks for the WhatsApp Inbox page (Phase 2.0).
 *
 * Read-only endpoints to start. Send endpoints + SSE land in 2.1+.
 */

import { useEffect } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { openSseStream } from "@/lib/sse";

export type ConversationListItem = {
  contact_id: string;
  contact_name: string;
  contact_company: string;
  last_message_at: string | null;
  last_message_preview: string;
  unread_count: number;
  window_expires_at: string | null;
  window_open: boolean;
};

export type ConversationListResponse = {
  conversations: ConversationListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type WAMessageOut = {
  id: number;
  direction: "in" | "out";
  status: string;
  text: string;
  media_type: string | null;
  media_path: string | null;
  media_caption: string | null;
  wa_message_id: string | null;
  error_code: string | null;
  error_detail: string | null;
  created_at: string;
};

export type ConversationDetail = {
  contact_id: string;
  contact_name: string;
  contact_company: string;
  contact_phone: string;
  contact_wa_id: string | null;
  consent_status: string;
  lifecycle: string;
  window_expires_at: string | null;
  window_open: boolean;
  last_inbound_at: string | null;
  messages: WAMessageOut[];
};

export type WATemplateOut = {
  id: number;
  name: string;
  language: string;
  category: string | null;
  status: string | null;
  body_text: string;
  header_format: string | null;
  header_asset_url: string | null;
  header_text: string | null;
  footer_text: string | null;
  variables: string[];
  // Phase 4.0 additions
  is_draft: boolean;
  tier: string;
  rejection_reason: string;
  submitted_at: string | null;
  quality_score: string | null;
  buttons: unknown[];
};

export type WATemplatesResponse = {
  templates: WATemplateOut[];
  total: number;
};

export type ConversationsQuery = {
  search?: string;
  archived?: boolean;
  page?: number;
  page_size?: number;
};

export function useConversations(q: ConversationsQuery = {}) {
  const params = new URLSearchParams();
  if (q.search) params.set("search", q.search);
  if (q.archived) params.set("archived", "true");
  if (q.page !== undefined) params.set("page", String(q.page));
  if (q.page_size !== undefined) params.set("page_size", String(q.page_size));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: [
      "wa",
      "conversations",
      { search: q.search ?? "", archived: !!q.archived, page: q.page ?? 0, page_size: q.page_size ?? 50 },
    ],
    queryFn: () => apiFetch<ConversationListResponse>(`/api/v2/wa/conversations${qs}`),
    placeholderData: keepPreviousData,
    // Phase 2.2: SSE drives invalidation, no polling needed.
  });
}

export function useConversationDetail(contactId: string | null) {
  return useQuery({
    queryKey: ["wa", "conversation", contactId],
    enabled: contactId !== null,
    queryFn: () => apiFetch<ConversationDetail>(`/api/v2/wa/conversations/${contactId}`),
    // Phase 2.2: SSE drives invalidation, no polling needed.
  });
}

export type TemplatesQuery = {
  category?: string;
  status?: string;
  tier?: string;
  search?: string;
  include_drafts?: boolean;
};

export function useWaTemplates(q: TemplatesQuery | string = {}) {
  // Backwards-compat: useWaTemplates("MARKETING") is still supported.
  const query: TemplatesQuery = typeof q === "string" ? { category: q } : q;
  const params = new URLSearchParams();
  if (query.category) params.set("category", query.category);
  if (query.status) params.set("status", query.status);
  if (query.tier) params.set("tier", query.tier);
  if (query.search) params.set("search", query.search);
  if (query.include_drafts) params.set("include_drafts", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: ["wa", "templates", query],
    queryFn: () => apiFetch<WATemplatesResponse>(`/api/v2/wa/templates${qs}`),
    staleTime: 60 * 1000,
  });
}

/* ── write paths (Phase 2.1) ─────────────────────────────────────────── */

export type SendMessageRequest = {
  contact_id: string;
  text: string;
};

export type SendTemplateRequest = {
  contact_id: string;
  template_name: string;
  language?: string;
  variables?: string[];
};

/**
 * Send a text message in the open 24h window. Mutation invalidates the
 * affected conversation detail + the conversation list so previews
 * update immediately without waiting for the polling tick.
 */
export function useSendTextMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SendMessageRequest) =>
      apiFetch<WAMessageOut>("/api/v2/wa/messages", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (_msg, variables) => {
      qc.invalidateQueries({ queryKey: ["wa", "conversation", variables.contact_id] });
      qc.invalidateQueries({ queryKey: ["wa", "conversations"] });
    },
  });
}

/**
 * Send a pre-approved template. Always allowed (independent of window).
 * Successful template sends extend the 24h window — the cache invalidations
 * here refetch the chat detail so the composer unlocks client-side too.
 */
export function useSendTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SendTemplateRequest) =>
      apiFetch<WAMessageOut>("/api/v2/wa/template-sends", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (_msg, variables) => {
      qc.invalidateQueries({ queryKey: ["wa", "conversation", variables.contact_id] });
      qc.invalidateQueries({ queryKey: ["wa", "conversations"] });
    },
  });
}

/* ── Template Studio (Phase 4.1a) ─────────────────────────────────────── */

export type TemplateUpsert = {
  name?: string;
  language?: string;
  category?: string;
  body_text?: string;
  header_format?: string | null;
  header_text?: string | null;
  header_asset_url?: string | null;
  footer_text?: string | null;
  buttons?: unknown[];
};

export function useWaTemplate(templateId: number | null) {
  return useQuery({
    queryKey: ["wa", "template", templateId],
    enabled: templateId !== null,
    queryFn: () => apiFetch<WATemplateOut>(`/api/v2/wa/templates/${templateId}`),
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TemplateUpsert) =>
      apiFetch<WATemplateOut>("/api/v2/wa/templates", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wa", "templates"] });
    },
  });
}

export function useSaveTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: TemplateUpsert }) =>
      apiFetch<WATemplateOut>(`/api/v2/wa/templates/${id}/save`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wa", "templates"] });
      qc.invalidateQueries({ queryKey: ["wa", "template"] });
    },
  });
}

export function useSubmitTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<WATemplateOut>(`/api/v2/wa/templates/${id}/submit`, {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wa", "templates"] });
      qc.invalidateQueries({ queryKey: ["wa", "template"] });
    },
  });
}

export function useSyncTemplates() {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ job_id: string }>("/api/v2/wa/templates/sync", {
        method: "POST",
      }),
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v2/wa/templates/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wa", "templates"] });
    },
  });
}

/**
 * Subscribe to live conversation events via SSE. Each `message` event
 * invalidates the affected conversation's detail query plus the list,
 * so React Query refetches them on demand. No polling.
 *
 * Phase 2.2: replaces the previous 30s/15s refetchInterval pattern.
 */
export function useWaLiveStream() {
  const qc = useQueryClient();

  useEffect(() => {
    const dispose = openSseStream("/api/v2/wa/stream", {
      onEvent: (e) => {
        if (e.event !== "message") return;
        try {
          const payload = JSON.parse(e.data) as { contact_id?: string };
          if (payload.contact_id) {
            qc.invalidateQueries({
              queryKey: ["wa", "conversation", payload.contact_id],
            });
          }
          qc.invalidateQueries({ queryKey: ["wa", "conversations"] });
        } catch {
          // ignore malformed payloads
        }
      },
      // Errors are non-fatal: openSseStream auto-reconnects with
      // exponential backoff. We don't surface them to the UI.
      onError: () => {},
    });
    return dispose;
  }, [qc]);
}

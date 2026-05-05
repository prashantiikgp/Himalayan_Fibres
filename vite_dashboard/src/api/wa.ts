/**
 * /api/v2/wa/* hooks for the WhatsApp Inbox page (Phase 2.0).
 *
 * Read-only endpoints to start. Send endpoints + SSE land in 2.1+.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

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
    // Light polling for now — Phase 2.1 swaps this for SSE.
    refetchInterval: 30_000,
  });
}

export function useConversationDetail(contactId: string | null) {
  return useQuery({
    queryKey: ["wa", "conversation", contactId],
    enabled: contactId !== null,
    queryFn: () => apiFetch<ConversationDetail>(`/api/v2/wa/conversations/${contactId}`),
    refetchInterval: 15_000,
  });
}

export function useWaTemplates(category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  return useQuery({
    queryKey: ["wa", "templates", category ?? "all"],
    queryFn: () => apiFetch<WATemplatesResponse>(`/api/v2/wa/templates${qs}`),
    staleTime: 5 * 60 * 1000,
  });
}

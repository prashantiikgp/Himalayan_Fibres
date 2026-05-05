/**
 * /api/v2/broadcasts hooks (Phase 3.0).
 *
 * Read-only unified list to start; Compose endpoints (audience-preview,
 * cost-estimate, send, schedule) land in 3.1+.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export type BroadcastChannel = "whatsapp" | "email";

export type BroadcastListItem = {
  id: string;
  channel: BroadcastChannel;
  name: string;
  template_id: string;
  segment_id: string | null;
  status: string;
  total_recipients: number;
  total_sent: number;
  total_failed: number;
  sent_at: string | null;
  scheduled_at: string | null;
  created_at: string;
  updated_at: string | null;
};

export type BroadcastListResponse = {
  broadcasts: BroadcastListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type BroadcastsQuery = {
  channel?: BroadcastChannel;
  status?: string;
  search?: string;
  page?: number;
  page_size?: number;
};

export function useBroadcastsList(q: BroadcastsQuery = {}) {
  const params = new URLSearchParams();
  if (q.channel) params.set("channel", q.channel);
  if (q.status) params.set("status", q.status);
  if (q.search) params.set("search", q.search);
  if (q.page !== undefined) params.set("page", String(q.page));
  if (q.page_size !== undefined) params.set("page_size", String(q.page_size));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: [
      "broadcasts",
      "list",
      {
        channel: q.channel ?? "all",
        status: q.status ?? "all",
        search: q.search ?? "",
        page: q.page ?? 0,
        page_size: q.page_size ?? 50,
      },
    ],
    queryFn: () => apiFetch<BroadcastListResponse>(`/api/v2/broadcasts${qs}`),
    placeholderData: keepPreviousData,
  });
}

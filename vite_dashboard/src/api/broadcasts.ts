/**
 * /api/v2/broadcasts hooks (Phase 3.0).
 *
 * Read-only unified list to start; Compose endpoints (audience-preview,
 * cost-estimate, send, schedule) land in 3.1+.
 */

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
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

/* ── Compose endpoints (Phase 3.1) ────────────────────────────────────── */

export type BroadcastFiltersIn = {
  segment_id?: string | null;
  countries?: string[];
  tags?: string[];
  lifecycles?: string[];
  consents?: string[];
  max_recipients?: number;
};

export type AudienceBreakdownItem = { label: string; count: number };

export type AudiencePreviewResponse = {
  total_in_segment: number;
  eligible_on_channel: number;
  final_recipients: number;
  excluded_by_channel: number;
  excluded_by_filters: number;
  consent: AudienceBreakdownItem[];
  geography: AudienceBreakdownItem[];
  lifecycle: AudienceBreakdownItem[];
  customer_type: AudienceBreakdownItem[];
};

export type CostBreakdownItem = {
  country: string;
  recipients: number;
  rate: number;
  currency: string;
  symbol: string;
  subtotal: number;
  display: string;
};

export type CostEstimateResponse = {
  recipients: number;
  per_message_display: string;
  total_display: string;
  currency: string;
  category: string | null;
  breakdown: CostBreakdownItem[];
  est_delivery_seconds: number;
};

export type SendBroadcastResponse = {
  broadcast_id: number;
  name: string;
  total_recipients: number;
  total_sent: number;
  total_failed: number;
  status: string;
};

export function useAudiencePreview(
  channel: BroadcastChannel,
  filters: BroadcastFiltersIn,
  enabled = true,
) {
  return useQuery({
    queryKey: ["broadcasts", "audience-preview", { channel, filters }],
    enabled,
    queryFn: () =>
      apiFetch<AudiencePreviewResponse>("/api/v2/broadcasts/audience-preview", {
        method: "POST",
        body: JSON.stringify({ channel, filters }),
      }),
    staleTime: 5_000,
  });
}

export function useCostEstimate(
  channel: BroadcastChannel,
  category: string,
  filters: BroadcastFiltersIn,
  enabled = true,
) {
  return useQuery({
    queryKey: ["broadcasts", "cost-estimate", { channel, category, filters }],
    enabled,
    queryFn: () =>
      apiFetch<CostEstimateResponse>("/api/v2/broadcasts/cost-estimate", {
        method: "POST",
        body: JSON.stringify({ channel, category, filters }),
      }),
    staleTime: 5_000,
  });
}

export type QueueEmailBroadcastResponse = {
  job_id: string;
  estimated_recipients: number;
};

export type JobStatusResponse = {
  job_id: string;
  job_type: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  message: string;
  result: Record<string, unknown> | null;
};

export function useQueueEmailBroadcast() {
  return useMutation({
    mutationFn: (body: {
      name: string;
      template_id: string;
      subject?: string;
      filters: BroadcastFiltersIn;
    }) =>
      apiFetch<QueueEmailBroadcastResponse>("/api/v2/broadcasts/email", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

/**
 * Poll a queued broadcast's job status. Stops auto-refetching once the
 * job reaches a terminal state. Returns null while idle (no jobId).
 */
export function useJobProgress(jobId: string | null) {
  return useQuery({
    queryKey: ["jobs", jobId],
    enabled: jobId !== null,
    queryFn: () =>
      apiFetch<JobStatusResponse>(`/api/v2/jobs/${jobId}/status`),
    refetchInterval: (query) => {
      const data = query.state.data as JobStatusResponse | undefined;
      if (!data) return 1000;
      return data.status === "done" || data.status === "failed" ? false : 1000;
    },
  });
}

export function useSendWaBroadcast() {
  return useMutation({
    mutationFn: (body: {
      name: string;
      template_id: string;
      filters: BroadcastFiltersIn;
      subject?: string;
    }) =>
      apiFetch<SendBroadcastResponse>("/api/v2/broadcasts/wa", {
        method: "POST",
        body: JSON.stringify({ ...body, channel: "whatsapp" }),
      }),
  });
}

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

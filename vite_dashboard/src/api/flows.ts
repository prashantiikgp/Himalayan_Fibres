/**
 * /api/v2/flows hooks (Phase 5.0).
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export type FlowOut = {
  id: number;
  name: string;
  description: string;
  channel: "email" | "whatsapp";
  is_active: boolean;
  step_count: number;
  created_at: string;
};

export type FlowsResponse = {
  flows: FlowOut[];
  total: number;
};

export type FlowRunOut = {
  id: number;
  flow_id: number;
  segment_id: string | null;
  status: string;
  current_step: number;
  total_contacts: number;
  total_sent: number;
  total_failed: number;
  started_at: string;
  next_step_at: string | null;
};

export type FlowRunsResponse = {
  runs: FlowRunOut[];
  total: number;
};

export type FlowsQuery = {
  active_only?: boolean;
  channel?: "email" | "whatsapp";
};

export function useFlows(q: FlowsQuery = {}) {
  const params = new URLSearchParams();
  if (q.active_only) params.set("active_only", "true");
  if (q.channel) params.set("channel", q.channel);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: ["flows", q],
    queryFn: () => apiFetch<FlowsResponse>(`/api/v2/flows${qs}`),
    staleTime: 30 * 1000,
  });
}

export function useFlowRuns(flowId: number | null, limit = 50) {
  return useQuery({
    queryKey: ["flows", "runs", flowId, limit],
    enabled: flowId !== null,
    queryFn: () =>
      apiFetch<FlowRunsResponse>(
        `/api/v2/flows/${flowId}/runs?limit=${limit}`,
      ),
  });
}

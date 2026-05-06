/**
 * /api/v2/flows — Phase 5.0 list + Phase 7.7 memberships + Phase 7.8 detail.
 *
 * Hooks return the raw response shape; mutations invalidate the
 * relevant query keys per PLAN_flows §4.3 so optimistic UX feels live.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { apiFetch } from "./client";

// ─── Types ───────────────────────────────────────────────────────────

export type FlowChannel = "email" | "whatsapp" | "multi";

export type TriggerType = "manual" | "lifecycle" | "tag" | "inbound_keyword";

export type MembershipStatus =
  | "active"
  | "waiting_event"
  | "paused"
  | "completed"
  | "failed"
  | "stopped";

export type StepRunStatus = "sent" | "failed" | "skipped";

export type FlowOut = {
  id: number;
  name: string;
  slug: string | null;
  description: string;
  channel: FlowChannel;
  is_active: boolean;
  step_count: number;
  trigger_type: TriggerType | string;
  trigger_config: Record<string, unknown>;
  active_count: number;
  created_at: string;
};

export type FlowDetailOut = FlowOut & {
  steps: Array<Record<string, unknown>>;
  counts: Partial<Record<MembershipStatus, number>>;
};

export type FlowsResponse = { flows: FlowOut[]; total: number };

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
export type FlowRunsResponse = { runs: FlowRunOut[]; total: number };

export type FlowMembershipOut = {
  id: number;
  flow_id: number;
  flow_name: string;
  flow_slug: string | null;
  contact_id: string;
  contact_name: string;
  contact_email: string | null;
  status: MembershipStatus | string;
  current_step_index: number;
  total_steps: number;
  started_at: string;
  last_step_at: string | null;
  next_fire_at: string | null;
  trigger_source: string;
  trigger_actor: string;
  error: string;
};

export type FlowMembershipDetail = FlowMembershipOut & {
  flow_trigger_type: TriggerType | string;
  current_step: Record<string, unknown> | null;
};

export type FlowMembershipsResponse = {
  memberships: FlowMembershipOut[];
  total: number;
};

export type FlowMembershipDetailsResponse = {
  memberships: FlowMembershipDetail[];
  total: number;
};

export type FlowStepRunOut = {
  id: number;
  membership_id: number;
  step_index: number;
  channel: "email" | "whatsapp";
  fired_at: string;
  status: StepRunStatus;
  template_slug: string;
  message_ref: string;
  error: string;
};

export type FlowStepRunsResponse = {
  step_runs: FlowStepRunOut[];
  total: number;
};

export type FlowsQuery = {
  active_only?: boolean;
  channel?: FlowChannel;
};

// ─── Cache keys (centralized so mutations + components agree) ────────

export const flowKeys = {
  all: ["flows"] as const,
  list: (q: FlowsQuery) => ["flows", q] as const,
  detail: (flowId: number) => ["flows", "detail", flowId] as const,
  memberships: (flowId: number, status?: string) =>
    ["flows", "memberships", flowId, status ?? "all"] as const,
  stepRuns: (flowId: number, status?: string) =>
    ["flows", "step_runs", flowId, status ?? "all"] as const,
  contactMemberships: (contactId: string, includePast?: boolean) =>
    [
      "contacts",
      "detail",
      contactId,
      "flow-memberships",
      includePast ?? true,
    ] as const,
} as const;

// ─── Read hooks ──────────────────────────────────────────────────────

export function useFlows(q: FlowsQuery = {}) {
  const params = new URLSearchParams();
  if (q.active_only) params.set("active_only", "true");
  if (q.channel) params.set("channel", q.channel);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: flowKeys.list(q),
    queryFn: () => apiFetch<FlowsResponse>(`/api/v2/flows${qs}`),
    staleTime: 30 * 1000,
  });
}

export function useFlow(flowId: number | null) {
  return useQuery({
    queryKey: flowKeys.detail(flowId ?? 0),
    enabled: flowId !== null,
    queryFn: () => apiFetch<FlowDetailOut>(`/api/v2/flows/${flowId}`),
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

export function useFlowMemberships(
  flowId: number | null,
  q: { status?: MembershipStatus | "all"; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (q.status && q.status !== "all") params.set("status", q.status);
  if (q.limit) params.set("limit", String(q.limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: flowKeys.memberships(flowId ?? 0, q.status),
    enabled: flowId !== null,
    queryFn: () =>
      apiFetch<FlowMembershipsResponse>(
        `/api/v2/flows/${flowId}/memberships${qs}`,
      ),
    staleTime: 30 * 1000,
  });
}

export function useFlowStepRuns(
  flowId: number | null,
  q: { status?: StepRunStatus | "all"; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (q.status && q.status !== "all") params.set("status", q.status);
  if (q.limit) params.set("limit", String(q.limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: flowKeys.stepRuns(flowId ?? 0, q.status),
    enabled: flowId !== null,
    queryFn: () =>
      apiFetch<FlowStepRunsResponse>(
        `/api/v2/flows/${flowId}/step-runs${qs}`,
      ),
    staleTime: 60 * 1000,
  });
}

export function useContactFlowMemberships(
  contactId: string | null,
  q: { include_past?: boolean } = {},
) {
  const params = new URLSearchParams();
  if (q.include_past === false) params.set("include_past", "false");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: flowKeys.contactMemberships(contactId ?? "", q.include_past),
    enabled: contactId !== null,
    queryFn: () =>
      apiFetch<FlowMembershipDetailsResponse>(
        `/api/v2/contacts/${contactId}/flow-memberships${qs}`,
      ),
    staleTime: 30 * 1000,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────

function invalidateMembership(qc: QueryClient, flowId: number, contactId: string) {
  qc.invalidateQueries({ queryKey: ["flows", "memberships", flowId] });
  qc.invalidateQueries({
    queryKey: ["contacts", "detail", contactId, "flow-memberships"],
  });
  qc.invalidateQueries({ queryKey: ["flows", "detail", flowId] });
  qc.invalidateQueries({ queryKey: ["flows"] });
}

export function useAssignFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: {
      flowId: number;
      contactId: string;
      actor?: string;
    }) =>
      apiFetch<FlowMembershipOut>(
        `/api/v2/flows/${params.flowId}/memberships`,
        {
          method: "POST",
          body: JSON.stringify({
            contact_id: params.contactId,
            actor: params.actor ?? "user",
          }),
        },
      ),
    onSuccess: (_data, variables) => {
      invalidateMembership(qc, variables.flowId, variables.contactId);
    },
  });
}

/**
 * Optimistic status flip — used by stop / pause / resume. Snapshots
 * the cached membership lists, patches the row in place, and rolls
 * back on error. After settle, invalidates so the server state wins.
 */
function useStatusMutation(args: {
  pathSuffix: "stop" | "pause" | "resume";
  optimisticStatus: MembershipStatus;
  reArm: boolean;
}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (membershipId: number) =>
      apiFetch<FlowMembershipOut>(
        `/api/v2/flow-memberships/${membershipId}/${args.pathSuffix}`,
        { method: "POST" },
      ),
    onMutate: async (membershipId) => {
      // Snapshot every queryCache entry that might hold this membership.
      const snapshots: Array<[readonly unknown[], unknown]> = [];
      qc.getQueryCache()
        .findAll({ predicate: (q) => Array.isArray(q.queryKey) })
        .forEach((q) => {
          const data = q.state.data as
            | FlowMembershipsResponse
            | FlowMembershipDetailsResponse
            | undefined;
          if (
            !data ||
            !("memberships" in data) ||
            !Array.isArray(data.memberships)
          ) {
            return;
          }
          if (!data.memberships.some((m) => m.id === membershipId)) return;
          snapshots.push([q.queryKey, data]);
          const patched = {
            ...data,
            memberships: data.memberships.map((m) =>
              m.id === membershipId
                ? {
                    ...m,
                    status: args.optimisticStatus,
                    next_fire_at: args.reArm ? new Date().toISOString() : null,
                  }
                : m,
            ),
          } as typeof data;
          qc.setQueryData(q.queryKey, patched);
        });
      return { snapshots };
    },
    onError: (_err, _vars, ctx) => {
      ctx?.snapshots.forEach(([key, data]) => qc.setQueryData(key, data));
    },
    onSettled: (data) => {
      // We don't always know flowId/contactId from the membershipId alone,
      // so invalidate broadly. The server returns the updated membership
      // — use that to invalidate precisely.
      if (data) {
        invalidateMembership(qc, data.flow_id, data.contact_id);
      } else {
        qc.invalidateQueries({ queryKey: ["flows"] });
        qc.invalidateQueries({ queryKey: ["contacts"] });
      }
    },
  });
}

export const useStopMembership = () =>
  useStatusMutation({
    pathSuffix: "stop",
    optimisticStatus: "stopped",
    reArm: false,
  });

export const usePauseMembership = () =>
  useStatusMutation({
    pathSuffix: "pause",
    optimisticStatus: "paused",
    reArm: false,
  });

export const useResumeMembership = () =>
  useStatusMutation({
    pathSuffix: "resume",
    optimisticStatus: "active",
    reArm: true,
  });

export type MarkSampleShippedRequest = {
  tracking_id: string;
  courier_name: string;
};

export type MarkSampleShippedResponse = {
  tag_added: boolean;
  memberships_updated: number[];
  new_memberships_from_trigger: number;
};

export function useMarkSampleShipped() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: {
      contactId: string;
      body: MarkSampleShippedRequest;
    }) =>
      apiFetch<MarkSampleShippedResponse>(
        `/api/v2/contacts/${params.contactId}/mark-sample-shipped`,
        {
          method: "POST",
          body: JSON.stringify(params.body),
        },
      ),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({
        queryKey: ["contacts", "detail", variables.contactId, "flow-memberships"],
      });
      qc.invalidateQueries({
        queryKey: ["contacts", "detail", variables.contactId],
      });
      qc.invalidateQueries({ queryKey: ["flows"] });
    },
  });
}

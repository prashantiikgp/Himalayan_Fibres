/**
 * <FlowDetailPage> — /flows/:flowId
 *
 * Three tabs (Members default, Steps, Step Runs) per PLAN_flows §3.2.
 * Each tab fetches independently; a panel's loading or error state
 * does NOT cascade to its siblings (panel-independent skeletons).
 */

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import {
  useFlow,
  useFlowMemberships,
  useFlowStepRuns,
  usePauseMembership,
  useResumeMembership,
  useStopMembership,
  type FlowMembershipOut,
  type MembershipStatus,
  type StepRunStatus,
} from "@/api/flows";
import { ChannelPill, TriggerPill } from "./components/FlowsTable";
import { MembershipStatusPill } from "./components/MembershipStatusPill";
import { formatRelative } from "@/lib/format";
import { STRINGS, tFormat } from "@/lib/strings";
import { cn } from "@/lib/utils";
import type { ApiError } from "@/lib/queryClient";

const STATUS_FILTERS: Array<{
  value: "all" | MembershipStatus;
  label: string;
}> = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "waiting_event", label: "Waiting event" },
  { value: "paused", label: "Paused" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "stopped", label: "Stopped" },
];

const STEP_RUN_FILTERS: Array<{
  value: "all" | StepRunStatus;
  label: string;
}> = [
  { value: "all", label: "All" },
  { value: "sent", label: "Sent" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

export function FlowDetailPage() {
  const { flowId: flowIdParam } = useParams<{ flowId: string }>();
  const flowId = flowIdParam ? parseInt(flowIdParam, 10) : null;
  const navigate = useNavigate();
  const t = STRINGS.flows.detail;

  const { data: flow, isLoading: flowLoading, error: flowError } = useFlow(flowId);

  return (
    <div className="flex flex-col gap-3 p-2">
      <button
        type="button"
        onClick={() => navigate("/flows")}
        className="self-start text-xs text-primary hover:underline"
      >
        {t.backToList}
      </button>

      {flowError && (
        <p role="alert" className="rounded-md border border-danger/40 bg-danger/5 p-card text-sm text-danger">
          {t.flowNotFound}
        </p>
      )}

      {flowLoading && !flow && (
        <div className="rounded-md border border-border bg-card p-card text-sm text-text-muted">
          Loading flow…
        </div>
      )}

      {flow && (
        <>
          {/* Header card */}
          <header className="flex flex-col gap-2 rounded-md border border-border bg-card p-card">
            <h1 className="text-2xl font-semibold text-text">{flow.name}</h1>
            <div className="flex flex-wrap gap-2">
              <TriggerPill
                triggerType={flow.trigger_type}
                triggerConfig={flow.trigger_config}
              />
              <ChannelPill channel={flow.channel} />
              <span className="rounded-pill border border-border bg-card px-2 py-0.5 text-[10px] uppercase tracking-wider text-text-muted">
                {flow.step_count} steps
              </span>
              {!flow.is_active && (
                <span className="rounded-pill border border-border bg-card px-2 py-0.5 text-[10px] uppercase tracking-wider text-text-muted">
                  Inactive
                </span>
              )}
            </div>
            {flow.description && (
              <p className="text-xs text-text-muted">{flow.description}</p>
            )}
          </header>

          {/* KPI cards */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <KpiCard label={t.kpiActive} value={flow.counts.active ?? 0} tone="primary" />
            <KpiCard label={t.kpiWaitingEvent} value={flow.counts.waiting_event ?? 0} tone="warning" />
            <KpiCard label={t.kpiCompleted} value={flow.counts.completed ?? 0} tone="success" />
            <KpiCard label={t.kpiFailed} value={flow.counts.failed ?? 0} tone="danger" />
          </div>

          {/* Tabs */}
          <Tabs defaultValue="members">
            <TabsList>
              <TabsTrigger value="members">{t.tabMembers}</TabsTrigger>
              <TabsTrigger value="steps">{t.tabSteps}</TabsTrigger>
              <TabsTrigger value="step_runs">{t.tabStepRuns}</TabsTrigger>
            </TabsList>

            <TabsContent value="members">
              <MembersTab flowId={flow.id} flowSlug={flow.slug ?? ""} />
            </TabsContent>
            <TabsContent value="steps">
              <StepsTab steps={flow.steps} />
            </TabsContent>
            <TabsContent value="step_runs">
              <StepRunsTab flowId={flow.id} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}

// ─── KPI card ────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "primary" | "warning" | "success" | "danger";
}) {
  const toneClass = {
    primary: "text-primary",
    warning: "text-warning",
    success: "text-success",
    danger: "text-danger",
  }[tone];
  return (
    <div className="rounded-md border border-border bg-card p-card">
      <div className="text-[10px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className={cn("mt-1 text-2xl font-semibold tabular-nums", toneClass)}>
        {value}
      </div>
    </div>
  );
}

// ─── Members tab ─────────────────────────────────────────────────────

function MembersTab({ flowId }: { flowId: number; flowSlug: string }) {
  const t = STRINGS.flows.detail;
  const [statusFilter, setStatusFilter] =
    useState<"all" | MembershipStatus>("active");
  const { data, isLoading, error } = useFlowMemberships(flowId, {
    status: statusFilter,
    limit: 200,
  });

  return (
    <div className="flex flex-col gap-3 p-card">
      <div className="flex items-center gap-2">
        <label className="text-xs text-text-muted">{t.statusFilterLabel}</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
        >
          {STATUS_FILTERS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {error && (
        <p role="alert" className="text-xs text-danger">
          {error.message}
        </p>
      )}
      {isLoading && (
        <p className="text-xs text-text-muted">Loading memberships…</p>
      )}
      {data && data.memberships.length === 0 && !isLoading && (
        <p className="text-xs text-text-muted">{t.membersEmpty}</p>
      )}
      {data && data.memberships.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="bg-card text-left text-text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">{t.colContact}</th>
                <th className="px-3 py-2 font-medium">{t.colStatus}</th>
                <th className="px-3 py-2 font-medium">{t.colStep}</th>
                <th className="px-3 py-2 font-medium">{t.colNextFire}</th>
                <th className="px-3 py-2 font-medium">{t.colStarted}</th>
                <th className="px-3 py-2 font-medium">{t.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {data.memberships.map((m) => (
                <MemberRow key={m.id} member={m} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MemberRow({ member }: { member: FlowMembershipOut }) {
  const t = STRINGS.flows.detail;
  const [confirm, setConfirm] = useState<{ kind: "stop" | "pause" } | null>(null);
  const stop = useStopMembership();
  const pause = usePauseMembership();
  const resume = useResumeMembership();

  const isTerminal =
    member.status === "completed" ||
    member.status === "failed" ||
    member.status === "stopped";
  const canPause = member.status === "active" || member.status === "waiting_event";
  const canResume = member.status === "paused";
  const canStop = !isTerminal;

  const inFlight = stop.isPending || pause.isPending || resume.isPending;
  const inlineError = stop.error || pause.error || resume.error;
  const errMsg = inlineError ? friendlyTransitionError(inlineError) : null;

  const name = member.contact_name || member.contact_id;
  return (
    <tr className="border-t border-border align-top">
      <td className="px-3 py-2">
        <div className="font-medium text-text">{name}</div>
        {member.contact_email && (
          <div className="text-text-muted">{member.contact_email}</div>
        )}
      </td>
      <td className="px-3 py-2">
        <MembershipStatusPill status={member.status} />
        {member.error && (
          <div className="mt-1 max-w-[180px] truncate text-[10px] text-danger" title={member.error}>
            {member.error}
          </div>
        )}
      </td>
      <td className="px-3 py-2">
        Step {member.current_step_index + 1} of {member.total_steps}
      </td>
      <td className="px-3 py-2 text-text-muted">
        {member.next_fire_at ? formatRelative(member.next_fire_at) : "—"}
      </td>
      <td className="px-3 py-2 text-text-muted">
        {formatRelative(member.started_at)}
      </td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-1">
          {canPause && (
            <Button
              variant="outline"
              size="sm"
              disabled={inFlight}
              onClick={() => setConfirm({ kind: "pause" })}
            >
              {t.pauseAction}
            </Button>
          )}
          {canResume && (
            <Button
              variant="outline"
              size="sm"
              disabled={inFlight}
              onClick={() => resume.mutate(member.id)}
            >
              {t.resumeAction}
            </Button>
          )}
          {canStop && (
            <Button
              variant="destructive"
              size="sm"
              disabled={inFlight}
              onClick={() => setConfirm({ kind: "stop" })}
            >
              {t.stopAction}
            </Button>
          )}
        </div>
        {errMsg && (
          <p role="alert" className="mt-1 text-[10px] text-danger">{errMsg}</p>
        )}
      </td>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.kind === "stop"
            ? tFormat(t.confirmStopTitle, { name })
            : tFormat(t.confirmPauseTitle, { name })
        }
        description={
          confirm?.kind === "stop" ? t.confirmStopBody : t.confirmPauseBody
        }
        confirmLabel={confirm?.kind === "stop" ? t.stopAction : t.pauseAction}
        destructive={confirm?.kind === "stop"}
        isPending={inFlight}
        onConfirm={() => {
          if (confirm?.kind === "stop") stop.mutate(member.id);
          else pause.mutate(member.id);
          setConfirm(null);
        }}
      />
    </tr>
  );
}

function friendlyTransitionError(err: Error | ApiError | null): string {
  const t = STRINGS.contacts.drawer.flowsTab;
  if (err && typeof err === "object" && "status" in err) {
    const status = (err as { status: number }).status;
    if (status === 409) return t.errorBadTransition;
  }
  return t.errorGeneric;
}

// ─── Steps tab ───────────────────────────────────────────────────────

function StepsTab({ steps }: { steps: Array<Record<string, unknown>> }) {
  if (!steps.length) {
    return (
      <p className="p-card text-xs text-text-muted">
        This flow has no steps configured yet.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2 p-card">
      {steps.map((step, i) => (
        <StepCard key={i} step={step} index={i} />
      ))}
    </div>
  );
}

function StepCard({ step, index }: { step: Record<string, unknown>; index: number }) {
  const channel = ((step.channel as string) ?? "email").toLowerCase();
  const channels =
    channel === "both" ? ["email", "whatsapp"] : channel === "whatsapp" ? ["whatsapp"] : ["email"];

  const event = step.trigger_event as { type?: string; value?: string } | undefined;
  const delay = step.delay_after_prev as { value?: number; unit?: string } | undefined;

  return (
    <div className="rounded-md border border-border bg-card p-card">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded-pill border border-border bg-bg px-2 py-0.5 text-[10px] uppercase tracking-wider text-text-muted">
          Step {index}
        </span>
        {channels.map((c) => (
          <span
            key={c}
            className={cn(
              "rounded-pill border px-2 py-0.5 text-[10px] uppercase tracking-wider",
              c === "whatsapp"
                ? "border-success/40 bg-success/10 text-success"
                : "border-primary/40 bg-primary/10 text-primary",
            )}
          >
            {c}
          </span>
        ))}
      </div>
      {channels.includes("email") && Boolean(step.template_slug) && (
        <div className="text-xs">
          <span className="text-text-muted">Email template: </span>
          <code className="rounded bg-bg px-1 text-text">{String(step.template_slug)}</code>
        </div>
      )}
      {channels.includes("whatsapp") && Boolean(step.wa_template) && (
        <div className="text-xs">
          <span className="text-text-muted">WA template: </span>
          <code className="rounded bg-bg px-1 text-text">{String(step.wa_template)}</code>
        </div>
      )}
      {event && (
        <div className="mt-1 text-xs">
          <span className="text-text-muted">Waits for: </span>
          <code className="rounded bg-warning/10 px-1 text-warning">
            {event.type}_added: {event.value}
          </code>
        </div>
      )}
      {!event && delay && typeof delay.value === "number" && (
        <div className="mt-1 text-xs text-text-muted">
          Delay: {delay.value} {delay.unit ?? "days"}{" "}
          {delay.value === 0 && "(immediate)"}
        </div>
      )}
      {Array.isArray(step.conditions) && step.conditions.length > 0 && (
        <div className="mt-1 text-xs text-text-muted">
          Conditions:{" "}
          {(step.conditions as Array<Record<string, unknown>>)
            .map((c) => `${c.field} ${c.op}${c.values ? ` (${(c.values as string[]).join(",")})` : ""}`)
            .join(" · ")}
        </div>
      )}
    </div>
  );
}

// ─── Step Runs tab ───────────────────────────────────────────────────

function StepRunsTab({ flowId }: { flowId: number }) {
  const t = STRINGS.flows.detail;
  const [statusFilter, setStatusFilter] =
    useState<"all" | StepRunStatus>("all");
  const { data, isLoading, error } = useFlowStepRuns(flowId, {
    status: statusFilter,
    limit: 200,
  });

  return (
    <div className="flex flex-col gap-3 p-card">
      <div className="flex items-center gap-2">
        <label className="text-xs text-text-muted">{t.statusFilterLabel}</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
        >
          {STEP_RUN_FILTERS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {error && <p role="alert" className="text-xs text-danger">{error.message}</p>}
      {isLoading && <p className="text-xs text-text-muted">Loading step runs…</p>}
      {data && data.step_runs.length === 0 && !isLoading && (
        <p className="text-xs text-text-muted">{t.stepRunsEmpty}</p>
      )}
      {data && data.step_runs.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="bg-card text-left text-text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">{t.colFired}</th>
                <th className="px-3 py-2 font-medium">{t.colStep}</th>
                <th className="px-3 py-2 font-medium">{t.colChannel}</th>
                <th className="px-3 py-2 font-medium">{t.colTemplate}</th>
                <th className="px-3 py-2 font-medium">{t.colStatus}</th>
                <th className="px-3 py-2 font-medium">{t.colError}</th>
              </tr>
            </thead>
            <tbody>
              {data.step_runs.map((r) => (
                <tr key={r.id} className="border-t border-border align-top">
                  <td className="px-3 py-2 text-text-muted">
                    {formatRelative(r.fired_at)}
                  </td>
                  <td className="px-3 py-2">{r.step_index}</td>
                  <td className="px-3 py-2 uppercase text-text-muted">{r.channel}</td>
                  <td className="px-3 py-2">
                    <code className="rounded bg-card px-1">{r.template_slug || "—"}</code>
                  </td>
                  <td className="px-3 py-2">
                    <RunStatusPill status={r.status} />
                  </td>
                  <td className="max-w-[300px] truncate px-3 py-2 text-danger" title={r.error}>
                    {r.error || ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RunStatusPill({ status }: { status: StepRunStatus }) {
  const tone =
    status === "sent"
      ? "border-success/40 bg-success/10 text-success"
      : status === "failed"
      ? "border-danger/40 bg-danger/10 text-danger"
      : "border-border bg-card text-text-muted";
  return (
    <span
      className={cn(
        "inline-block rounded-pill border px-2 py-0.5 text-[10px] uppercase tracking-wider",
        tone,
      )}
    >
      {status}
    </span>
  );
}

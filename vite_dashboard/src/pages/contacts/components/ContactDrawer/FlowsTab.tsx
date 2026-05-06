/**
 * <FlowsTab> — body of the contact drawer's "Flows" tab (PLAN_flows §3.3).
 *
 * Three sections:
 *   1. Active flows  — one card per membership in {active, waiting_event, paused}
 *      with Pause/Resume/Stop actions and the conditional "Mark sample
 *      shipped" inline-expand form (PLAN_flows §3.7).
 *   2. Past flows    — collapsed accordion of completed/stopped/failed.
 *   3. Add to flow   — dropdown of active flows the contact is NOT
 *      already enrolled in, plus an "Add" button.
 */

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import {
  useAssignFlow,
  useContactFlowMemberships,
  useFlows,
  useMarkSampleShipped,
  usePauseMembership,
  useResumeMembership,
  useStopMembership,
  type FlowMembershipDetail,
  type FlowOut,
} from "@/api/flows";
import { TriggerPill } from "@/pages/flows/components/FlowsTable";
import { MembershipStatusPill } from "@/pages/flows/components/MembershipStatusPill";
import { formatRelative } from "@/lib/format";
import { STRINGS, tFormat } from "@/lib/strings";
import { cn } from "@/lib/utils";
import type { ApiError } from "@/lib/queryClient";

const ACTIVE_STATUSES = new Set(["active", "waiting_event", "paused"]);

export function FlowsTab({ contactId }: { contactId: string }) {
  const t = STRINGS.contacts.drawer.flowsTab;
  const { data, isLoading, error } = useContactFlowMemberships(contactId);
  const { data: allFlows } = useFlows({ active_only: true });

  const memberships = data?.memberships ?? [];
  const active = memberships.filter((m) =>
    ACTIVE_STATUSES.has(m.status as string),
  );
  const past = memberships.filter(
    (m) => !ACTIVE_STATUSES.has(m.status as string),
  );

  return (
    <div className="flex flex-col gap-4 py-2">
      {error && (
        <p role="alert" className="rounded-md border border-danger/40 bg-danger/5 px-3 py-2 text-xs text-danger">
          {error.message}
        </p>
      )}
      {isLoading && <p className="text-xs text-text-muted">Loading flows…</p>}

      {/* Active flows */}
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          {t.activeHeader}
        </h3>
        {active.length === 0 ? (
          <p className="text-xs text-text-muted">{t.noActiveFlows}</p>
        ) : (
          active.map((m) => (
            <ActiveFlowCard key={m.id} membership={m} contactId={contactId} />
          ))
        )}
      </section>

      {/* Past flows (collapsed) */}
      {past.length > 0 && <PastFlowsSection memberships={past} />}

      {/* Add to flow */}
      <AddToFlowSection
        contactId={contactId}
        flows={allFlows?.flows ?? []}
        excludeFlowIds={new Set(memberships.map((m) => m.flow_id))}
      />
    </div>
  );
}

// ─── Active flow card ───────────────────────────────────────────────

function ActiveFlowCard({
  membership,
  contactId,
}: {
  membership: FlowMembershipDetail;
  contactId: string;
}) {
  const t = STRINGS.contacts.drawer.flowsTab;

  const [confirm, setConfirm] = useState<{ kind: "stop" | "pause" } | null>(null);
  const stop = useStopMembership();
  const pause = usePauseMembership();
  const resume = useResumeMembership();
  const inFlight = stop.isPending || pause.isPending || resume.isPending;
  const inlineError = stop.error || pause.error || resume.error;

  // Mark Sample Shipped only renders for the right shape of step.
  const showMarkShipped = isMarkSampleShippedEligible(membership);
  const [markOpen, setMarkOpen] = useState(false);

  const stepProgress = tFormat(t.stepProgress, {
    n: membership.current_step_index + 1,
    total: membership.total_steps,
  });

  const eventLabel = readEventLabel(membership);
  const nextLine = eventLabel
    ? tFormat(t.nextFireWaiting, { event: eventLabel })
    : membership.next_fire_at
    ? tFormat(t.nextFireAt, { when: formatRelative(membership.next_fire_at) })
    : "—";

  const flowName = membership.flow_name || `Flow #${membership.flow_id}`;

  const canPause = membership.status === "active" || membership.status === "waiting_event";
  const canResume = membership.status === "paused";

  return (
    <div className="rounded-md border border-border bg-card p-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text">{flowName}</span>
          <TriggerPill
            triggerType={membership.flow_trigger_type}
            triggerConfig={{}}
          />
        </div>
        <MembershipStatusPill status={membership.status} />
      </div>

      <div className="mt-2 text-xs text-text">{stepProgress}</div>

      {/* Progress bar */}
      <div className="mt-2 h-2 w-full rounded-full bg-bg">
        <div
          className="h-2 rounded-full bg-primary"
          style={{
            width: `${membership.total_steps > 0
              ? Math.min(100, ((membership.current_step_index + 0.5) / membership.total_steps) * 100)
              : 0}%`,
          }}
        />
      </div>

      <div className="mt-2 text-xs text-text-muted">{nextLine}</div>
      <div className="text-xs text-text-muted">
        {tFormat(t.startedAt, { when: formatRelative(membership.started_at) })}
      </div>

      {membership.error && (
        <p
          role="alert"
          className="mt-2 max-w-full break-words rounded border border-warning/40 bg-warning/5 px-2 py-1 text-[11px] text-warning"
        >
          {STRINGS.flows.detail.partialFailureBadge}: {membership.error}
        </p>
      )}

      {/* Actions */}
      <div className="mt-3 flex flex-wrap gap-2">
        {showMarkShipped && (
          <Button
            variant="default"
            size="sm"
            onClick={() => setMarkOpen((v) => !v)}
          >
            {t.markSampleShipped}
          </Button>
        )}
        {canPause && (
          <Button
            variant="outline"
            size="sm"
            disabled={inFlight}
            onClick={() => setConfirm({ kind: "pause" })}
          >
            {t.pause}
          </Button>
        )}
        {canResume && (
          <Button
            variant="outline"
            size="sm"
            disabled={inFlight}
            onClick={() => resume.mutate(membership.id)}
          >
            {t.resume}
          </Button>
        )}
        <Button
          variant="destructive"
          size="sm"
          disabled={inFlight}
          onClick={() => setConfirm({ kind: "stop" })}
        >
          {t.stop}
        </Button>
      </div>

      {inlineError && (
        <p role="alert" className="mt-2 text-xs text-danger">
          {friendlyError(inlineError)}
        </p>
      )}

      {/* Mark Sample Shipped inline-expand form */}
      {showMarkShipped && markOpen && (
        <MarkSampleShippedForm
          contactId={contactId}
          onClose={() => setMarkOpen(false)}
        />
      )}

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.kind === "stop"
            ? tFormat(STRINGS.flows.detail.confirmStopTitle, { name: flowName })
            : tFormat(STRINGS.flows.detail.confirmPauseTitle, { name: flowName })
        }
        description={
          confirm?.kind === "stop"
            ? STRINGS.flows.detail.confirmStopBody
            : STRINGS.flows.detail.confirmPauseBody
        }
        confirmLabel={
          confirm?.kind === "stop"
            ? STRINGS.flows.detail.stopAction
            : STRINGS.flows.detail.pauseAction
        }
        destructive={confirm?.kind === "stop"}
        isPending={inFlight}
        onConfirm={() => {
          if (confirm?.kind === "stop") stop.mutate(membership.id);
          else pause.mutate(membership.id);
          setConfirm(null);
        }}
      />
    </div>
  );
}

// ─── Mark Sample Shipped inline form ────────────────────────────────

function MarkSampleShippedForm({
  contactId,
  onClose,
}: {
  contactId: string;
  onClose: () => void;
}) {
  const t = STRINGS.contacts.drawer.flowsTab;
  const [trackingId, setTrackingId] = useState("");
  const [courierName, setCourierName] = useState("");
  const mark = useMarkSampleShipped();

  const valid = trackingId.trim().length > 0 && courierName.trim().length > 0;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;
    mark.mutate(
      {
        contactId,
        body: {
          tracking_id: trackingId.trim(),
          courier_name: courierName.trim(),
        },
      },
      { onSuccess: () => onClose() },
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-3 flex flex-col gap-2 rounded-md border border-primary/30 bg-primary/5 p-3"
    >
      <div className="text-xs font-semibold text-primary">{t.markShippedTitle}</div>
      <p className="text-[11px] text-text-muted">{t.markShippedHelp}</p>

      <label className="flex flex-col gap-1 text-[11px] text-text">
        {t.markShippedTrackingLabel}
        <input
          type="text"
          maxLength={128}
          required
          value={trackingId}
          onChange={(e) => setTrackingId(e.target.value)}
          className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
          placeholder="BD123456789"
        />
      </label>

      <label className="flex flex-col gap-1 text-[11px] text-text">
        {t.markShippedCourierLabel}
        <input
          type="text"
          maxLength={64}
          required
          value={courierName}
          onChange={(e) => setCourierName(e.target.value)}
          className="h-8 rounded-md border border-border bg-card px-2 text-xs text-text"
          placeholder="BlueDart"
        />
      </label>

      {mark.error && (
        <p role="alert" className="text-xs text-danger">
          {friendlyError(mark.error)}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClose}
          disabled={mark.isPending}
        >
          {t.markShippedCancel}
        </Button>
        <Button
          type="submit"
          variant="default"
          size="sm"
          disabled={!valid || mark.isPending}
        >
          {mark.isPending ? "…" : t.markShippedSubmit}
        </Button>
      </div>
    </form>
  );
}

// ─── Past flows section ─────────────────────────────────────────────

function PastFlowsSection({
  memberships,
}: {
  memberships: FlowMembershipDetail[];
}) {
  const t = STRINGS.contacts.drawer.flowsTab;
  const [open, setOpen] = useState(false);

  return (
    <section className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-text-muted hover:text-text"
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        {t.pastHeader} ({memberships.length})
      </button>
      {open && (
        <div className="flex flex-col gap-1">
          {memberships.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-xs"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-text">{m.flow_name}</span>
                <MembershipStatusPill status={m.status} />
              </div>
              <span className="text-text-muted">
                {m.last_step_at
                  ? tFormat(t.endedAt, { when: formatRelative(m.last_step_at) })
                  : "—"}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ─── Add to flow ────────────────────────────────────────────────────

function AddToFlowSection({
  contactId,
  flows,
  excludeFlowIds,
}: {
  contactId: string;
  flows: FlowOut[];
  excludeFlowIds: Set<number>;
}) {
  const t = STRINGS.contacts.drawer.flowsTab;
  const [pick, setPick] = useState<string>("");
  const assign = useAssignFlow();

  const options = useMemo(
    () => flows.filter((f) => !excludeFlowIds.has(f.id)),
    [flows, excludeFlowIds],
  );

  function handleAdd() {
    const id = parseInt(pick, 10);
    if (!Number.isFinite(id)) return;
    assign.mutate(
      { flowId: id, contactId },
      {
        onSuccess: () => setPick(""),
      },
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
        {t.addToFlow}
      </h3>
      <div className="flex gap-2">
        <select
          value={pick}
          onChange={(e) => setPick(e.target.value)}
          className="h-9 flex-1 rounded-md border border-border bg-card px-2 text-xs text-text"
          disabled={assign.isPending}
        >
          <option value="">{t.addPlaceholder}</option>
          {options.map((f) => (
            <option key={f.id} value={String(f.id)}>
              {f.name}
            </option>
          ))}
        </select>
        <Button
          variant="default"
          size="sm"
          disabled={!pick || assign.isPending}
          onClick={handleAdd}
        >
          {assign.isPending ? "…" : t.addButton}
        </Button>
      </div>
      {assign.error && (
        <p role="alert" className="text-xs text-danger">
          {friendlyError(assign.error)}
        </p>
      )}
    </section>
  );
}

// ─── helpers ────────────────────────────────────────────────────────

function isMarkSampleShippedEligible(m: FlowMembershipDetail): boolean {
  if (m.flow_slug !== "sample_dispatch") return false;
  if (m.status !== "waiting_event") return false;
  const ev = m.current_step?.trigger_event as
    | { type?: string; value?: string }
    | undefined;
  return ev?.type === "tag" && ev?.value === "samples_shipped";
}

function readEventLabel(m: FlowMembershipDetail): string | null {
  if (m.status !== "waiting_event") return null;
  const ev = m.current_step?.trigger_event as
    | { value?: string }
    | undefined;
  return ev?.value ?? null;
}

function friendlyError(err: Error | ApiError | null): string {
  const t = STRINGS.contacts.drawer.flowsTab;
  if (err && typeof err === "object" && "status" in err) {
    const status = (err as { status: number }).status;
    if (status === 404) return t.errorContactNotFound;
    if (status === 409) {
      // 409 from assign means already enrolled; from pause/resume/stop
      // means bad transition; from mark-shipped means already shipped.
      const url = (err as { url?: string }).url ?? "";
      if (url.includes("/memberships")) return t.errorAlreadyEnrolled;
      if (url.includes("/mark-sample-shipped")) return t.errorAlreadyShipped;
      return t.errorBadTransition;
    }
    if (status === 400) return t.errorFlowInactive;
  }
  return t.errorGeneric;
}

// Suppress unused-import warning when cn is referenced only in SSR builds.
void cn;

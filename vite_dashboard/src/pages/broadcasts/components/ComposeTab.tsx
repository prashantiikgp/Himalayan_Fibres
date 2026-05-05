/**
 * <ComposeTab> — broadcast Compose tab on /broadcasts.
 *
 * Phase 3.1 ships WhatsApp send only (sync). Email queue + scheduler
 * land in 3.1b. The B3 fix (audience funnel as sticky header) and
 * B10 fix (type-SEND-to-confirm) are wired here.
 */

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Calendar, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSegments } from "@/api/contacts";
import { useWaTemplates } from "@/api/wa";
import {
  useAudiencePreview,
  useCostEstimate,
  useQueueEmailBroadcast,
  useSendWaBroadcast,
  type BroadcastChannel,
  type BroadcastFiltersIn,
} from "@/api/broadcasts";
import { AudienceFunnel } from "./AudienceFunnel";
import { CostEstimateCards } from "./CostEstimateCards";
import { ScheduleSheet } from "./ScheduleSheet";
import { SendConfirmDialog } from "./SendConfirmDialog";
import { SendProgress } from "./SendProgress";

export function ComposeTab({
  lockedChannel,
}: {
  /** Phase 6.3: when set, hides the channel toggle and locks Compose
   * to one channel. /wa-broadcasts and /email-broadcasts pass this so
   * each page is single-purpose. The legacy /broadcasts page leaves
   * this undefined and keeps the URL-driven toggle. */
  lockedChannel?: BroadcastChannel;
} = {}) {
  const [params, setParams] = useSearchParams();
  // B11: sidebar deep-links pass `?channel=...` to pre-select the
  // channel toggle. Default WhatsApp when omitted.
  const channelParam = params.get("channel");
  const initialChannel: BroadcastChannel =
    lockedChannel ??
    (channelParam === "email" ? "email" : "whatsapp");
  const [channel, setChannel] = useState<BroadcastChannel>(initialChannel);

  // Keep the toggle in sync if the URL changes (navigating between
  // sidebar entries while the page is mounted). Skip when locked.
  useEffect(() => {
    if (lockedChannel) {
      if (channel !== lockedChannel) setChannel(lockedChannel);
      return;
    }
    if (channelParam === "email" && channel !== "email") setChannel("email");
    if (channelParam === "whatsapp" && channel !== "whatsapp") setChannel("whatsapp");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelParam, lockedChannel]);
  const [name, setName] = useState("");
  const [segmentId, setSegmentId] = useState<string>("all_opted_in");
  const [templateName, setTemplateName] = useState<string>("");
  const [subject, setSubject] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [completed, setCompleted] = useState<{
    name: string;
    sent: number;
    failed: number;
  } | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduledOk, setScheduledOk] = useState<string | null>(null);

  const { data: segData } = useSegments();
  const { data: tplData } = useWaTemplates({ status: "APPROVED" });

  const filters: BroadcastFiltersIn = useMemo(
    () => ({ segment_id: segmentId === "all" ? null : segmentId }),
    [segmentId],
  );

  const { data: audience, isFetching: audienceLoading } = useAudiencePreview(
    channel,
    filters,
  );
  const selectedTemplate = tplData?.templates.find((t) => t.name === templateName);
  const category = selectedTemplate?.category ?? "MARKETING";
  const { data: cost, isFetching: costLoading } = useCostEstimate(
    channel,
    category.toLowerCase(),
    filters,
    channel === "whatsapp" ? !!templateName : true,
  );

  const sendWaMutation = useSendWaBroadcast();
  const queueEmailMutation = useQueueEmailBroadcast();
  const isSending = sendWaMutation.isPending || queueEmailMutation.isPending;

  const segmentLabel =
    segData?.segments.find((s) => s.id === segmentId)?.name ?? segmentId;

  // Email allows the template-id to be a free-text slug; we don't gate
  // on it being in the WA templates list.
  const hasTemplate = channel === "whatsapp" ? !!templateName : !!templateName;
  const canOpenConfirm =
    name.trim().length > 0 &&
    hasTemplate &&
    (audience?.final_recipients ?? 0) > 0;

  function handleSendClick() {
    setSubmitError(null);
    if (!canOpenConfirm) return;
    setConfirmOpen(true);
  }

  function handleConfirm() {
    if (!canOpenConfirm) return;
    setSubmitError(null);
    setActiveJobId(null);

    if (channel === "whatsapp") {
      sendWaMutation.mutate(
        { name: name.trim(), template_id: templateName, filters },
        {
          onSuccess: (res) => {
            setCompleted({ name: res.name, sent: res.total_sent, failed: res.total_failed });
            setConfirmOpen(false);
            setName("");
            setTemplateName("");
          },
          onError: (err) =>
            setSubmitError(err instanceof Error ? err.message : "Send failed"),
        },
      );
    } else {
      queueEmailMutation.mutate(
        {
          name: name.trim(),
          template_id: templateName,
          subject: subject.trim() || undefined,
          filters,
        },
        {
          onSuccess: (res) => {
            // Email is async — keep the form populated so the user
            // sees progress against the same audience preview.
            setActiveJobId(res.job_id);
            setConfirmOpen(false);
          },
          onError: (err) =>
            setSubmitError(err instanceof Error ? err.message : "Queue failed"),
        },
      );
    }
  }

  return (
    <div className="flex flex-col gap-4 p-card">
      <AudienceFunnel
        data={audience}
        isLoading={audienceLoading}
        segmentLabel={segmentLabel}
      />

      {completed && (
        <div
          role="status"
          className="rounded-md border border-success/40 bg-success/10 p-3 text-sm text-success"
        >
          Sent <code>{completed.name}</code> — {completed.sent} delivered, {completed.failed} failed.
        </div>
      )}

      {scheduledOk && (
        <div
          role="status"
          className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning"
        >
          Scheduled — fires at {new Date(scheduledOk).toLocaleString()}. The scheduler
          checks every minute. Cancel from the History tab while it's still pending.
        </div>
      )}

      {activeJobId && (
        <SendProgress
          jobId={activeJobId}
          recipientCount={audience?.final_recipients ?? 0}
        />
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendClick();
          }}
          className="flex flex-col gap-3"
        >
          {/* Phase 6.3: when channel is locked by the parent route,
              hide the toggle entirely. Each /wa-broadcasts and
              /email-broadcasts page sets lockedChannel. */}
          {!lockedChannel && (
            <Field label="Channel" id="bc-channel">
              <div className="inline-flex rounded-md border border-border bg-card p-0.5">
                {(["whatsapp", "email"] as BroadcastChannel[]).map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => {
                      setChannel(c);
                      setTemplateName("");
                      const next = new URLSearchParams(params);
                      next.set("channel", c);
                      setParams(next, { replace: true });
                    }}
                    className={
                      channel === c
                        ? "rounded px-3 py-1 text-xs font-medium bg-primary text-white"
                        : "rounded px-3 py-1 text-xs text-text-muted hover:text-text"
                    }
                  >
                    {c === "whatsapp" ? "WhatsApp" : "Email"}
                  </button>
                ))}
              </div>
            </Field>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Broadcast name" id="bc-name">
              <Input
                id="bc-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={channel === "whatsapp" ? "WA: April B2B intro" : "Email: April B2B intro"}
                required
              />
            </Field>
            <Field label="Audience" id="bc-segment">
              <select
                id="bc-segment"
                value={segmentId}
                onChange={(e) => setSegmentId(e.target.value)}
                className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
              >
                <option value="all_opted_in">All opted-in</option>
                {segData?.segments.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.member_count})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Template" id="bc-template" className="col-span-2">
              {channel === "whatsapp" ? (
                <select
                  id="bc-template"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
                  required
                >
                  <option value="">— Pick an approved template —</option>
                  {tplData?.templates.map((t) => (
                    <option key={t.id} value={t.name}>
                      {t.name} ({t.category ?? "?"}, {t.variables.length} var{t.variables.length === 1 ? "" : "s"})
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  id="bc-template"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="Email template slug (e.g. b2b_introduction)"
                  required
                />
              )}
            </Field>
            {channel === "email" && (
              <Field label="Subject (optional)" id="bc-subject" className="col-span-2">
                <Input
                  id="bc-subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Override the template subject — empty = use default"
                />
              </Field>
            )}
          </div>

          <CostEstimateCards data={cost} isLoading={costLoading} />

          {submitError && (
            <p role="alert" className="text-sm text-danger">
              {submitError}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            {channel === "email" && (
              <Button
                type="button"
                variant="outline"
                disabled={!canOpenConfirm || isSending}
                onClick={() => {
                  setSubmitError(null);
                  setScheduleOpen(true);
                }}
              >
                <Calendar className="mr-1 h-4 w-4" /> Schedule
              </Button>
            )}
            <Button
              type="submit"
              disabled={!canOpenConfirm || isSending}
            >
              <Send className="mr-1 h-4 w-4" /> Send Now
            </Button>
          </div>
        </form>

        <aside className="flex flex-col gap-2 rounded-md border border-border bg-card/40 p-card text-xs text-text-muted">
          <h3 className="text-sm font-semibold text-text">Notes</h3>
          <ul className="list-disc space-y-1 pl-4">
            <li>WA Send is synchronous — small batches finish in seconds.</li>
            <li>Email Send queues in the background — progress shown above.</li>
            <li>Template send opens a fresh 24h window per recipient.</li>
            <li>Send confirmation requires typing <code>SEND</code>.</li>
          </ul>
        </aside>
      </div>

      <SendConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        recipientCount={audience?.final_recipients ?? 0}
        costDisplay={cost?.total_display ?? "—"}
        segmentLabel={segmentLabel}
        templateName={templateName || "—"}
        isPending={isSending}
        errorMessage={submitError}
        onConfirm={handleConfirm}
      />

      <ScheduleSheet
        open={scheduleOpen}
        onOpenChange={setScheduleOpen}
        recipientCount={audience?.final_recipients ?? 0}
        templateName={templateName}
        isPending={queueEmailMutation.isPending}
        errorMessage={submitError}
        onConfirm={(iso) => {
          setSubmitError(null);
          queueEmailMutation.mutate(
            {
              name: name.trim(),
              template_id: templateName,
              subject: subject.trim() || undefined,
              filters,
              scheduled_at: iso,
            },
            {
              onSuccess: () => {
                setScheduleOpen(false);
                setScheduledOk(iso);
                setName("");
                setTemplateName("");
              },
              onError: (err) =>
                setSubmitError(err instanceof Error ? err.message : "Schedule failed"),
            },
          );
        }}
      />
    </div>
  );
}

function Field({
  label,
  id,
  children,
  className = "",
}: {
  label: string;
  id: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <Label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </Label>
      {children}
    </div>
  );
}

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
  useEmailTemplate,
  useEmailTemplates,
} from "@/api/email_templates";
import {
  useAudiencePreview,
  useCostEstimate,
  useQueueEmailBroadcast,
  useSendWaBroadcast,
  type BroadcastChannel,
  type BroadcastFiltersIn,
} from "@/api/broadcasts";
import {
  EmailVariablesForm,
  buildDefaultValues,
  requiredVariableNames,
} from "@/components/email/EmailVariablesForm";
import { EmailRenderPreview } from "@/components/email/EmailRenderPreview";
import { TemplatePreview } from "@/components/wa/TemplatePreview";
import { WaTemplatePicker } from "@/components/wa/WaTemplatePicker";
import { extractPlaceholders } from "@/lib/wa-template-vars";
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
  const [emailTemplateId, setEmailTemplateId] = useState<number | null>(null);
  const [emailVars, setEmailVars] = useState<Record<string, string>>({});
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
  const { data: emailTplData } = useEmailTemplates({ active_only: true });
  const { data: emailTpl } = useEmailTemplate(
    channel === "email" ? emailTemplateId : null,
  );

  // When the picked email template changes, reset typed variables to its
  // defaults (filtered to non-auto-resolved names) so old values don't
  // leak into a different template's render.
  useEffect(() => {
    if (channel !== "email") return;
    if (!emailTpl) {
      setEmailVars({});
      // Keep templateName in sync with the picked template's slug — the
      // queue endpoint expects the slug, not the id.
      if (emailTemplateId === null) setTemplateName("");
      return;
    }
    setEmailVars(buildDefaultValues(emailTpl.variable_spec ?? null, "broadcast"));
    setTemplateName(emailTpl.slug);
  }, [channel, emailTemplateId, emailTpl]);

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

  // For email we now require the picked email template to be loaded so
  // we have its variable_spec — gate on the template object, not just
  // the typed slug. Required vars (excluding auto-resolved ones) must
  // also be filled before Send Now is enabled.
  const requiredEmailVars = useMemo(
    () => requiredVariableNames(emailTpl?.variable_spec ?? null, "broadcast"),
    [emailTpl?.variable_spec],
  );
  const allEmailVarsFilled = requiredEmailVars.every(
    (n) => (emailVars[n] ?? "").trim().length > 0,
  );
  const hasTemplate =
    channel === "whatsapp" ? !!templateName : !!emailTemplateId && !!emailTpl;
  const canOpenConfirm =
    name.trim().length > 0 &&
    hasTemplate &&
    (audience?.final_recipients ?? 0) > 0 &&
    (channel === "whatsapp" || allEmailVarsFilled);

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
            setEmailTemplateId(null);
            setEmailVars({});
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
          variables: emailVars,
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

      {/* Phase 8.4: 2-col redesign. Left = filters + actions. Right =
          KEY CARDS pinned on top + big phone-style preview filling the
          rest. Right column is a flex column (R5: no `position: sticky`,
          which is consistently fiddly inside grid cells). */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_5fr]">
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
                      setEmailTemplateId(null);
                      setEmailVars({});
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

          <Divider label="Template" />

          {channel === "whatsapp" ? (
            <WaTemplatePicker
              value={templateName || null}
              onChange={(name) => setTemplateName(name ?? "")}
              status="APPROVED"
              density="list"
            />
          ) : (
            <Field label="Template" id="bc-template">
              <select
                id="bc-template"
                value={emailTemplateId ?? ""}
                onChange={(e) =>
                  setEmailTemplateId(
                    e.target.value === "" ? null : Number(e.target.value),
                  )
                }
                className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
                required
              >
                <option value="">— Pick an active email template —</option>
                {emailTplData?.templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.email_type}, {t.required_variables.length} var
                    {t.required_variables.length === 1 ? "" : "s"})
                  </option>
                ))}
              </select>
            </Field>
          )}

          {channel === "email" && emailTpl && (
            <>
              <Divider label="Variables" />
              <div className="rounded-md border border-border bg-card/40 p-card">
                <p className="mb-2 text-[10px] text-text-muted">
                  Per-recipient values (first name, email, company) resolve
                  from each contact at send time and don't appear here.
                </p>
                <EmailVariablesForm
                  spec={emailTpl.variable_spec ?? null}
                  values={emailVars}
                  onChange={setEmailVars}
                  mode="broadcast"
                />
              </div>
            </>
          )}

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

        {/* RIGHT COLUMN — flex flex-col so KEY CARDS stay pinned on top
            and PreviewPane fills the remaining height. Per plan R5,
            this is intentionally NOT a CSS grid + position: sticky. */}
        <aside className="flex min-h-0 flex-col gap-3">
          <CostEstimateCards data={cost} isLoading={costLoading} />

          <div className="flex-1 overflow-y-auto rounded-md border border-border bg-card/40 p-card">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
              Template render — phone preview
            </h3>
            {channel === "whatsapp" ? (
              selectedTemplate ? (
                <TemplatePreview
                  template={selectedTemplate}
                  /* Broadcasts don't substitute {{name}}/{{1}} — they
                     resolve per-recipient at send time. Pass empty
                     dicts so renderPreview falls back to the literal
                     `{{varName}}` placeholder, which signals to the
                     operator: "this gets replaced per contact." */
                  headerVariables={{}}
                  bodyVariables={{}}
                  headerVarNames={extractPlaceholders(selectedTemplate.header_text ?? "")}
                  bodyVarNames={selectedTemplate.variables ?? []}
                  onHeaderVarsChange={() => {}}
                  onBodyVarsChange={() => {}}
                  showInputs={false}
                  style="phone"
                  inputIdPrefix="compose"
                />
              ) : (
                <EmptyPreviewHint message="Pick a template above to see the phone preview." />
              )
            ) : emailTemplateId !== null && emailTpl ? (
              <EmailRenderPreview
                templateId={emailTemplateId}
                variables={emailVars}
                subjectTemplateOverride={
                  subject.trim().length > 0 ? subject : null
                }
              />
            ) : (
              <EmptyPreviewHint message="Pick a template above to see the rendered preview." />
            )}
          </div>
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
              variables: emailVars,
              scheduled_at: iso,
            },
            {
              onSuccess: () => {
                setScheduleOpen(false);
                setScheduledOk(iso);
                setName("");
                setTemplateName("");
                setEmailTemplateId(null);
                setEmailVars({});
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

function Divider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 pt-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <div className="h-px flex-1 bg-border" aria-hidden="true" />
    </div>
  );
}

function EmptyPreviewHint({ message }: { message: string }) {
  return (
    <div className="flex h-full min-h-[300px] items-center justify-center text-xs text-text-muted">
      {message}
    </div>
  );
}

/**
 * <ComposeTab> — broadcast Compose tab on /broadcasts.
 *
 * Phase 3.1 ships WhatsApp send only (sync). Email queue + scheduler
 * land in 3.1b. The B3 fix (audience funnel as sticky header) and
 * B10 fix (type-SEND-to-confirm) are wired here.
 */

import { useMemo, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSegments } from "@/api/contacts";
import { useWaTemplates } from "@/api/wa";
import {
  useAudiencePreview,
  useCostEstimate,
  useSendWaBroadcast,
  type BroadcastFiltersIn,
} from "@/api/broadcasts";
import { AudienceFunnel } from "./AudienceFunnel";
import { CostEstimateCards } from "./CostEstimateCards";
import { SendConfirmDialog } from "./SendConfirmDialog";

export function ComposeTab() {
  const [name, setName] = useState("");
  const [segmentId, setSegmentId] = useState<string>("all_opted_in");
  const [templateName, setTemplateName] = useState<string>("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [completed, setCompleted] = useState<{
    name: string;
    sent: number;
    failed: number;
  } | null>(null);

  const { data: segData } = useSegments();
  const { data: tplData } = useWaTemplates({ status: "APPROVED" });

  const filters: BroadcastFiltersIn = useMemo(
    () => ({ segment_id: segmentId === "all" ? null : segmentId }),
    [segmentId],
  );

  const { data: audience, isFetching: audienceLoading } = useAudiencePreview(
    "whatsapp",
    filters,
  );
  const selectedTemplate = tplData?.templates.find((t) => t.name === templateName);
  const category = selectedTemplate?.category ?? "MARKETING";
  const { data: cost, isFetching: costLoading } = useCostEstimate(
    "whatsapp",
    category.toLowerCase(),
    filters,
    !!templateName,
  );

  const sendMutation = useSendWaBroadcast();

  const segmentLabel =
    segData?.segments.find((s) => s.id === segmentId)?.name ?? segmentId;
  const canOpenConfirm =
    name.trim().length > 0 &&
    !!templateName &&
    (audience?.final_recipients ?? 0) > 0;

  function handleSendClick() {
    setSubmitError(null);
    if (!canOpenConfirm) return;
    setConfirmOpen(true);
  }

  function handleConfirm() {
    if (!canOpenConfirm) return;
    setSubmitError(null);
    sendMutation.mutate(
      {
        name: name.trim(),
        template_id: templateName,
        filters,
      },
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendClick();
          }}
          className="flex flex-col gap-3"
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="Broadcast name" id="bc-name">
              <Input
                id="bc-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="WA: April B2B intro"
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
            </Field>
          </div>

          <CostEstimateCards data={cost} isLoading={costLoading} />

          {submitError && (
            <p role="alert" className="text-sm text-danger">
              {submitError}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="submit"
              disabled={!canOpenConfirm || sendMutation.isPending}
            >
              <Send className="mr-1 h-4 w-4" /> Send Now
            </Button>
          </div>
        </form>

        <aside className="flex flex-col gap-2 rounded-md border border-border bg-card/40 p-card text-xs text-text-muted">
          <h3 className="text-sm font-semibold text-text">Notes</h3>
          <ul className="list-disc space-y-1 pl-4">
            <li>WA Send is synchronous — small batches finish in seconds.</li>
            <li>Template send opens a fresh 24h window per recipient.</li>
            <li>Email queue + scheduler land in Phase 3.1b.</li>
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
        isPending={sendMutation.isPending}
        errorMessage={submitError}
        onConfirm={handleConfirm}
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

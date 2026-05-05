/**
 * <TemplateSheet> — slide-over for picking + sending a WA template.
 *
 * Phase 7.5: preview + variables-form logic extracted to the shared
 * <TemplatePreview> component (consumed by Studio too). This file owns
 * the contact-aware prefill (the only caller that has a contact in
 * scope), template picker dropdown, send mutation, and submit gating.
 */

import { useEffect, useMemo, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { TemplatePreview } from "@/components/wa/TemplatePreview";
import {
  extractPlaceholders,
  resolveVariableForContact,
} from "@/lib/wa-template-vars";
import {
  useConversationDetail,
  useSendTemplate,
  useWaTemplates,
  type WATemplateOut,
} from "@/api/wa";

type Labels = {
  title: string;
  send_button_label: string;
};

export function TemplateSheet({
  open,
  onOpenChange,
  contactId,
  contactName,
  labels,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contactId: string | null;
  contactName: string;
  labels: Labels;
}) {
  const { data, isLoading, error } = useWaTemplates();
  const { data: convData } = useConversationDetail(contactId);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const selected: WATemplateOut | null = useMemo(
    () => data?.templates.find((t) => t.name === selectedName) ?? null,
    [data, selectedName],
  );
  const [bodyVars, setBodyVars] = useState<Record<string, string>>({});
  const [headerVars, setHeaderVars] = useState<Record<string, string>>({});
  const sendMutation = useSendTemplate();
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Header placeholders are derived from header_text by scanning {{N}}
  // tokens — the DB doesn't store them separately. Body placeholders use
  // the `variables` field the API derives server-side at render time.
  const headerVarNames = useMemo(
    () => extractPlaceholders(selected?.header_text ?? ""),
    [selected?.header_text],
  );
  const bodyVarNames = useMemo(() => selected?.variables ?? [], [selected]);

  // Reset when the sheet closes or the contact changes.
  useEffect(() => {
    if (!open) {
      setSelectedName(null);
      setBodyVars({});
      setHeaderVars({});
      setSubmitError(null);
      sendMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, contactId]);

  // Auto-prefill variables when a template is picked, mirroring the
  // broadcast engine's _resolve_wa_variable map. User can still edit.
  useEffect(() => {
    if (!selected) {
      setBodyVars({});
      setHeaderVars({});
      setSubmitError(null);
      return;
    }
    const ctx = convData
      ? { contact_name: convData.contact_name, contact_company: convData.contact_company }
      : null;
    const nextBody: Record<string, string> = {};
    for (const name of bodyVarNames) {
      nextBody[name] = resolveVariableForContact(name, ctx);
    }
    const nextHeader: Record<string, string> = {};
    for (const name of headerVarNames) {
      nextHeader[name] = resolveVariableForContact(name, ctx);
    }
    setBodyVars(nextBody);
    setHeaderVars(nextHeader);
    setSubmitError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedName, convData?.contact_id]);

  const allFilled =
    bodyVarNames.every((v) => (bodyVars[v] ?? "").trim().length > 0) &&
    headerVarNames.every((v) => (headerVars[v] ?? "").trim().length > 0);

  function handleSend() {
    if (!contactId || !selected) return;
    setSubmitError(null);
    const bodyValues = bodyVarNames.map((v) => (bodyVars[v] ?? "").trim());
    const headerValues = headerVarNames.map((v) => (headerVars[v] ?? "").trim());
    sendMutation.mutate(
      {
        contact_id: contactId,
        template_name: selected.name,
        language: selected.language || "en_US",
        variables: bodyValues,
        header_variables: headerValues.length > 0 ? headerValues : undefined,
      },
      {
        onSuccess: () => onOpenChange(false),
        onError: (err) => setSubmitError(err instanceof Error ? err.message : "Send failed"),
      },
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md md:max-w-lg">
        <SheetHeader>
          <SheetTitle>{labels.title}</SheetTitle>
          <SheetDescription>
            {contactId ? `Sending to ${contactName}` : "Pick a contact first."}
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-4 overflow-auto px-card pb-card">
          <div className="flex flex-col gap-1">
            <Label htmlFor="tpl-pick" className="text-xs text-text-muted">Template</Label>
            <select
              id="tpl-pick"
              value={selectedName ?? ""}
              onChange={(e) => setSelectedName(e.target.value || null)}
              disabled={isLoading || !!error}
              className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <option value="">— Pick a template —</option>
              {data?.templates.map((t) => (
                <option key={t.id} value={t.name}>
                  {t.name} ({t.category ?? "?"}, {t.variables.length} var{t.variables.length === 1 ? "" : "s"})
                </option>
              ))}
            </select>
            {error && <p role="alert" className="text-xs text-danger">{error.message}</p>}
          </div>

          {selected && (
            <>
              {!selected.body_text && (
                <p className="rounded-md border border-warning/40 bg-warning/5 p-2 text-xs text-warning">
                  Body not synced from Meta. Run sync on the Templates page,
                  or this send will fail with "expected N parameters".
                </p>
              )}

              <TemplatePreview
                template={selected}
                headerVariables={headerVars}
                bodyVariables={bodyVars}
                headerVarNames={headerVarNames}
                bodyVarNames={bodyVarNames}
                onHeaderVarsChange={setHeaderVars}
                onBodyVarsChange={setBodyVars}
                style="card"
                inputIdPrefix="tplsheet"
              />

              {submitError && (
                <p role="alert" className="text-sm text-danger">{submitError}</p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                  disabled={sendMutation.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  onClick={handleSend}
                  disabled={!contactId || !allFilled || sendMutation.isPending}
                >
                  {sendMutation.isPending ? "Sending…" : labels.send_button_label}
                </Button>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/**
 * <TemplateSheet> — slide-over for picking + sending a WA template.
 *
 * The B1 fix lives here: the variables form renders **exactly N inputs**
 * (one per declared variable) in a non-scrolling vertical stack. v1's
 * Email Broadcast template editor pre-allocated 8 visible slots; this
 * version only renders what the template actually declares, in
 * first-appearance order, with no padding.
 */

import { useEffect, useMemo, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
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
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const selected: WATemplateOut | null = useMemo(
    () => data?.templates.find((t) => t.name === selectedName) ?? null,
    [data, selectedName],
  );
  const [vars, setVars] = useState<Record<string, string>>({});
  const sendMutation = useSendTemplate();
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Reset when the sheet closes or the contact changes.
  useEffect(() => {
    if (!open) {
      setSelectedName(null);
      setVars({});
      setSubmitError(null);
      sendMutation.reset();
    }
    // sendMutation.reset is stable; including it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, contactId]);

  // Reset variable values when the chosen template changes.
  useEffect(() => {
    setVars({});
    setSubmitError(null);
  }, [selectedName]);

  const variableNames = selected?.variables ?? [];
  const allFilled = variableNames.every((v) => (vars[v] ?? "").trim().length > 0);

  function handleSend() {
    if (!contactId || !selected) return;
    setSubmitError(null);
    // Collect values in the same order the API extracted them.
    const values = variableNames.map((v) => (vars[v] ?? "").trim());
    sendMutation.mutate(
      {
        contact_id: contactId,
        template_name: selected.name,
        language: selected.language || "en_US",
        variables: values,
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
            {contactId
              ? `Sending to ${contactName}`
              : "Pick a contact first."}
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
              <section>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Body
                </h3>
                <div className="rounded-md border border-border bg-card/40 p-3 text-sm text-text whitespace-pre-wrap">
                  {selected.body_text || "(empty body)"}
                </div>
                {selected.footer_text && (
                  <p className="mt-1 text-xs italic text-text-muted">{selected.footer_text}</p>
                )}
              </section>

              {/* B1 fix: render EXACTLY one input per declared variable, */}
              {/* in declaration order, in a non-scrolling stack. No */}
              {/* placeholder slots, no padding. */}
              {variableNames.length > 0 && (
                <section>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Variables ({variableNames.length})
                  </h3>
                  <div className="flex flex-col gap-2">
                    {variableNames.map((name) => (
                      <div key={name} className="flex flex-col gap-1">
                        <Label htmlFor={`tpl-var-${name}`} className="text-xs text-text-muted">
                          {/* Numeric placeholders ({{1}}) get a friendlier label */}
                          {/^\d+$/.test(name) ? `Variable ${name}` : name}
                        </Label>
                        <Input
                          id={`tpl-var-${name}`}
                          value={vars[name] ?? ""}
                          onChange={(e) => setVars({ ...vars, [name]: e.target.value })}
                          placeholder={/^\d+$/.test(name) ? `value for {{${name}}}` : `value for {{${name}}}`}
                        />
                      </div>
                    ))}
                  </div>
                </section>
              )}

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

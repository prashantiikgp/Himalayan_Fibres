/**
 * <EmailSendPage> — `/email-send` (Phase 7.1).
 *
 * Founder-style "send Prashant the order_confirmation now" flow:
 *   pick contact → pick template → fill vars → preview → Send
 *
 * Sends fire ONE email and write a single `email_sends` row with
 * `campaign_id=NULL` (NOT a 1-recipient broadcast). Per-day idempotency
 * dedupes accidental double clicks within the same UTC day.
 */

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { configLoader } from "@/loaders/configLoader";
import { HowToUse } from "@/components/layout/HowToUse";
import {
  useEmailTemplate,
  type EmailTemplateOut,
} from "@/api/email_templates";
import {
  useSendOneEmail,
  useUploadAttachment,
  type AttachmentRef,
} from "@/api/email_send";
import type { ContactRow } from "@/api/contacts";
import { ContactPicker } from "./components/ContactPicker";
import { EmailTemplatePicker } from "./components/EmailTemplatePicker";
import {
  EmailVariablesForm,
  buildDefaultValues,
  requiredVariableNames,
} from "@/components/email/EmailVariablesForm";
import { EmailRenderPreview } from "@/components/email/EmailRenderPreview";

export function EmailSendPage() {
  const cfg = configLoader.getPage("email_send");

  const [contact, setContact] = useState<ContactRow | null>(null);
  const [templateId, setTemplateId] = useState<number | null>(null);
  // Picker gives us a partial Template (without variable_spec) on first
  // change — useEmailTemplate(id) loads the full one and is the source
  // of truth for the variable spec.
  const { data: template } = useEmailTemplate(templateId);
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [subjectOverride, setSubjectOverride] = useState<string>("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<AttachmentRef[]>([]);
  const [attachKind, setAttachKind] = useState<string>("invoice");

  const sendMutation = useSendOneEmail();
  const uploadMutation = useUploadAttachment();

  // Reset form whenever the template changes — different vars, different
  // defaults. EmailVariablesForm seeds its own defaults on mount but we
  // need to clear on template-switch so old values don't leak.
  useEffect(() => {
    setVariables(buildDefaultValues(template?.variable_spec, "single"));
    setSubjectOverride("");
    setSubmitError(null);
    setResultMessage(null);
    setAttachments([]);
  }, [templateId, template?.variable_spec]);

  const requiredNames = useMemo(
    () => requiredVariableNames(template?.variable_spec, "single"),
    [template?.variable_spec],
  );

  const allRequiredFilled = requiredNames.every(
    (n) => (variables[n] ?? "").trim().length > 0,
  );
  const canSend =
    contact !== null &&
    templateId !== null &&
    allRequiredFilled &&
    !sendMutation.isPending;

  function handleSend() {
    if (!canSend || contact === null || templateId === null) return;
    setSubmitError(null);
    setResultMessage(null);
    sendMutation.mutate(
      {
        template_id: templateId,
        contact_id: contact.id,
        variables,
        subject_override: subjectOverride.trim() || null,
        attachments,
      },
      {
        onSuccess: (res) => {
          setResultMessage(
            res.success
              ? res.message
              : `Send failed — ${res.message}`,
          );
        },
        onError: (err) =>
          setSubmitError(err instanceof Error ? err.message : "Send failed"),
      },
    );
  }

  return (
    <div className="flex flex-col gap-2 p-2">
      <HowToUse pageTitle={cfg.page.title} howTo={cfg.page.how_to_use} />

      <div className="grid min-h-[calc(100vh-180px)] grid-cols-1 gap-2 lg:grid-cols-[minmax(340px,0.9fr)_minmax(520px,1.6fr)]">
        <section
          aria-label="Send email form"
          className="overflow-auto rounded-lg border border-border bg-card/40 p-card"
        >
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
                Recipient
              </h2>
              <ContactPicker
                selected={contact}
                onSelect={setContact}
                onClear={() => setContact(null)}
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Template
                </h2>
                {templateId !== null && (
                  <a
                    href={`/email-templates?id=${templateId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    title="Open this template in the editor (new tab)"
                  >
                    Edit template
                    <ExternalLink className="h-3 w-3" aria-hidden />
                  </a>
                )}
              </div>
              <EmailTemplatePicker
                value={templateId}
                onChange={(id) => setTemplateId(id)}
              />
            </div>

            {template && (
              <SubjectAndVarsBlock
                template={template}
                subjectOverride={subjectOverride}
                onSubjectChange={setSubjectOverride}
                variables={variables}
                onVariablesChange={setVariables}
              />
            )}

            {template && (
              <div>
                <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Attach a document
                </h2>
                <p className="mb-2 text-xs text-text-muted">
                  Uploads to secure storage; the file is attached to the
                  email and its download button is filled in automatically.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    aria-label="Document type"
                    value={attachKind}
                    onChange={(e) => setAttachKind(e.target.value)}
                    className="h-9 rounded-md border border-border bg-card px-2 text-sm"
                  >
                    <option value="invoice">Invoice / Proforma</option>
                    <option value="price_list">Price list</option>
                    <option value="document">Other document</option>
                  </select>
                  <Input
                    type="file"
                    aria-label="Choose document"
                    accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
                    className="max-w-[220px] text-sm"
                    disabled={uploadMutation.isPending}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (!f) return;
                      setSubmitError(null);
                      uploadMutation.mutate(
                        { file: f, kind: attachKind },
                        {
                          onSuccess: (ref) =>
                            setAttachments((prev) => [
                              ...prev.filter((a) => a.kind !== ref.kind),
                              ref,
                            ]),
                          onError: (err) =>
                            setSubmitError(
                              err instanceof Error
                                ? err.message
                                : "Upload failed",
                            ),
                        },
                      );
                      e.target.value = "";
                    }}
                  />
                  {uploadMutation.isPending && (
                    <span className="text-xs text-text-muted">Uploading…</span>
                  )}
                </div>
                {attachments.length > 0 && (
                  <ul className="mt-2 flex flex-col gap-1">
                    {attachments.map((a) => (
                      <li
                        key={a.kind + a.url}
                        className="flex items-center justify-between gap-2 rounded border border-border bg-card/60 px-2 py-1 text-xs"
                      >
                        <span className="truncate">
                          <span className="text-text-muted">[{a.kind}]</span>{" "}
                          {a.file_name}
                        </span>
                        <button
                          type="button"
                          className="text-danger hover:underline"
                          onClick={() =>
                            setAttachments((prev) =>
                              prev.filter((x) => x.url !== a.url),
                            )
                          }
                        >
                          remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {submitError && (
              <p role="alert" className="text-sm text-danger">
                {submitError}
              </p>
            )}
            {resultMessage && (
              <p
                role="status"
                className={
                  resultMessage.startsWith("Send failed")
                    ? "text-sm text-danger"
                    : "text-sm text-success"
                }
              >
                {resultMessage}
              </p>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                onClick={handleSend}
                disabled={!canSend}
              >
                <Send className="mr-1 h-4 w-4" />
                {sendMutation.isPending ? "Sending…" : "Send"}
              </Button>
            </div>
          </div>
        </section>

        <section
          aria-label="Email render preview"
          className="overflow-hidden rounded-lg border border-border bg-card/40 p-card"
        >
          <EmailRenderPreview
            templateId={templateId}
            variables={variables}
            contactId={contact?.id ?? null}
            subjectTemplateOverride={
              subjectOverride.trim().length > 0 ? subjectOverride : null
            }
            attachments={attachments}
          />
        </section>
      </div>
    </div>
  );
}

function SubjectAndVarsBlock({
  template,
  subjectOverride,
  onSubjectChange,
  variables,
  onVariablesChange,
}: {
  template: EmailTemplateOut;
  subjectOverride: string;
  onSubjectChange: (v: string) => void;
  variables: Record<string, string>;
  onVariablesChange: (next: Record<string, string>) => void;
}) {
  return (
    <>
      <div className="flex flex-col gap-1">
        <Label htmlFor="email-send-subject" className="text-xs text-text-muted">
          Subject (override)
        </Label>
        <Input
          id="email-send-subject"
          value={subjectOverride}
          onChange={(e) => onSubjectChange(e.target.value)}
          placeholder={template.subject_template || "(uses template default)"}
        />
      </div>

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
          Variables
        </h2>
        <EmailVariablesForm
          spec={template.variable_spec ?? null}
          values={variables}
          onChange={onVariablesChange}
          mode="single"
        />
      </div>
    </>
  );
}

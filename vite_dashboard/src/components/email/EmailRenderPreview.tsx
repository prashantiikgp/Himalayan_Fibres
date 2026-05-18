/**
 * <EmailRenderPreview> — sandboxed iframe that re-renders on every change.
 *
 * Posts the merged variable dict (+ optional html_content_override for
 * Studio's Advanced mode) to POST /api/v2/email/render-preview and feeds
 * the returned HTML into a sandboxed `<iframe srcDoc>`. Server-side
 * because seeded templates use `{% extends %}` which Jinja2 only resolves
 * server-side.
 *
 * Inputs change → 200ms debounce → mutation → iframe updates.
 *
 * Phase 7.1 (Day_4_improvememt/PLAN_email.md).
 */

import { useEffect, useMemo, useState } from "react";
import { useDebouncedValue } from "@/lib/hooks";
import { useRenderEmailPreview, type AttachmentRef } from "@/api/email_send";

type ViewportMode = "desktop" | "mobile";

export function EmailRenderPreview({
  templateId,
  variables,
  contactId,
  htmlContentOverride,
  subjectTemplateOverride,
  attachments,
}: {
  templateId: number | null;
  variables: Record<string, string>;
  contactId?: string | null;
  /** Studio Advanced-mode escape hatch — render this HTML instead of the
   * saved body. Used by EmailTemplateEditor so the user sees their
   * unsaved edits live. */
  htmlContentOverride?: string | null;
  /** Override the rendered subject. Used by ComposeTab + EmailSendPage
   * where the user can type a custom subject override. */
  subjectTemplateOverride?: string | null;
  /** Uploaded docs — surfaced as {kind}_url so the template's download
   * button shows in the preview. */
  attachments?: AttachmentRef[];
}) {
  const [viewport, setViewport] = useState<ViewportMode>("desktop");

  // Debounce the entire payload, not just the variables — the user might
  // also be typing in the html_content textarea (Studio).
  const debouncedVars = useDebouncedValue(variables, 200);
  const debouncedHtml = useDebouncedValue(htmlContentOverride ?? null, 200);
  const debouncedSubject = useDebouncedValue(subjectTemplateOverride ?? null, 200);
  // Stable key so the effect re-runs only when the attachment set changes.
  const attKey = useMemo(
    () => (attachments ?? []).map((a) => `${a.kind}:${a.url}`).join("|"),
    [attachments],
  );

  const mutation = useRenderEmailPreview();
  const { mutate, data, isPending, error } = mutation;

  useEffect(() => {
    if (templateId === null) return;
    mutate({
      template_id: templateId,
      variables: debouncedVars,
      contact_id: contactId ?? null,
      html_content_override: debouncedHtml,
      subject_template_override: debouncedSubject,
      attachments: attachments ?? [],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId, debouncedVars, debouncedHtml, debouncedSubject, contactId, attKey]);

  const subject = data?.subject ?? "";
  const html = data?.html ?? "";

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          Preview
        </h3>
        <div className="inline-flex rounded-md border border-border bg-card p-0.5 text-xs">
          {(["desktop", "mobile"] as ViewportMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setViewport(m)}
              className={
                viewport === m
                  ? "rounded px-2 py-0.5 bg-primary text-white"
                  : "rounded px-2 py-0.5 text-text-muted hover:text-text"
              }
            >
              {m === "desktop" ? "Desktop" : "Mobile"}
            </button>
          ))}
        </div>
      </div>

      {templateId === null ? (
        <div className="flex h-full items-center justify-center rounded-md border border-dashed border-border bg-card/40 p-card text-sm text-text-muted">
          Pick a template to see the preview.
        </div>
      ) : (
        <>
          <div className="rounded-md border border-border bg-card/40 p-2">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">
              Subject
            </div>
            <div
              className="truncate text-sm text-text"
              title={subject}
            >
              {subject || (isPending ? "Rendering…" : "(empty)")}
            </div>
          </div>

          {error ? (
            <div
              role="alert"
              className="rounded-md border border-danger/40 bg-danger/10 p-2 text-xs text-danger"
            >
              {error instanceof Error ? error.message : "Render failed"}
            </div>
          ) : null}

          <div className="flex min-h-[720px] flex-1 justify-center overflow-auto rounded-md border border-border bg-white">
            <iframe
              title="Email render preview"
              className={
                viewport === "mobile"
                  ? "min-h-[720px] w-[412px] max-w-full"
                  : "h-full min-h-[720px] w-full"
              }
              srcDoc={html || "<p style='color:#999;font-family:sans-serif;padding:24px'>(empty body)</p>"}
              sandbox=""
            />
          </div>

          <p className="text-[10px] text-text-muted">
            Rendered with the inputs above. Per-recipient variables (first
            name, email, etc.) resolve from the contact at send time.
          </p>
        </>
      )}
    </div>
  );
}

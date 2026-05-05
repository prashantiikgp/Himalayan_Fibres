/**
 * <EmailTemplateEditor> — right panel of /email-templates.
 *
 * Phase 7.3: the raw HTML body is hidden behind an "Advanced" toggle.
 * The default surface is rendered preview + typed variable inputs so the
 * founder isn't forced to read HTML to verify a template. Editing a
 * variable updates the preview live; editing the HTML in Advanced mode
 * also updates the preview live (in-memory override; saving still
 * persists the textarea content as before).
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import {
  useCreateEmailTemplate,
  useDeleteEmailTemplate,
  useEmailTemplate,
  useSaveEmailTemplate,
  type EmailTemplateUpsert,
  type EmailVariableSpec,
} from "@/api/email_templates";
import {
  EmailVariablesForm,
  buildDefaultValues,
} from "@/components/email/EmailVariablesForm";
import { EmailRenderPreview } from "@/components/email/EmailRenderPreview";

const EMAIL_TYPES = ["campaign", "transactional", "automation", "test"];

const EMPTY: EmailTemplateUpsert & { name: string; slug: string } = {
  name: "",
  slug: "",
  subject_template: "",
  html_content: "",
  email_type: "campaign",
  required_variables: [],
  category: "",
  is_active: true,
};

type Mode = "create" | "edit";

/** Synthesize a basic variable spec from a comma-separated `required`
 * field — for newly-created templates that don't have `variable_spec`
 * from the backend yet. */
function synthSpecFromRequired(names: string[]): EmailVariableSpec[] {
  return names.map((n) => ({
    name: n,
    label: n.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    type: "text",
    placeholder: `Sample ${n}`,
    example: "",
    required: true,
  }));
}

export function EmailTemplateEditor({
  templateId,
  mode,
  onCreated,
  onDeleted,
}: {
  templateId: number | null;
  mode: Mode;
  onCreated: (id: number) => void;
  onDeleted: () => void;
}) {
  const { data: loaded, isLoading, error } = useEmailTemplate(
    mode === "edit" ? templateId : null,
  );
  const [form, setForm] = useState<typeof EMPTY>(EMPTY);
  const [variablesText, setVariablesText] = useState("");
  const [previewVars, setPreviewVars] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const createMutation = useCreateEmailTemplate();
  const saveMutation = useSaveEmailTemplate();
  const deleteMutation = useDeleteEmailTemplate();

  useEffect(() => {
    if (mode === "create") {
      setForm({ ...EMPTY });
      setVariablesText("");
      setPreviewVars({});
      setSaveError(null);
      return;
    }
    if (loaded) {
      setForm({
        name: loaded.name,
        slug: loaded.slug,
        subject_template: loaded.subject_template,
        html_content: loaded.html_content,
        email_type: loaded.email_type,
        required_variables: loaded.required_variables,
        category: loaded.category,
        is_active: loaded.is_active,
      });
      setVariablesText(loaded.required_variables.join(", "));
      setPreviewVars(buildDefaultValues(loaded.variable_spec ?? null, "studio"));
      setSaveError(null);
    }
  }, [mode, loaded]);

  // Effective spec: prefer the backend-supplied one (rich, with example
  // values), fall back to a synth from the comma-separated `required`
  // field so the form still renders inputs while the user types.
  const effectiveSpec: EmailVariableSpec[] | null = useMemo(() => {
    if (loaded?.variable_spec && loaded.variable_spec.length > 0) {
      return loaded.variable_spec;
    }
    const names = variablesText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (names.length === 0) return null;
    return synthSpecFromRequired(names);
  }, [loaded?.variable_spec, variablesText]);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaveError(null);
    const variables = variablesText
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    const body: EmailTemplateUpsert = { ...form, required_variables: variables };

    if (mode === "create") {
      if (!form.name.trim() || !form.slug.trim()) {
        setSaveError("Name and slug are required.");
        return;
      }
      createMutation.mutate(body, {
        onSuccess: (t) => onCreated(t.id),
        onError: (err) =>
          setSaveError(err instanceof Error ? err.message : "Create failed"),
      });
    } else if (templateId !== null) {
      saveMutation.mutate(
        { id: templateId, body },
        {
          onError: (err) =>
            setSaveError(err instanceof Error ? err.message : "Save failed"),
        },
      );
    }
  }

  function performDelete() {
    if (templateId === null) return;
    deleteMutation.mutate(templateId, {
      onSuccess: () => {
        setConfirmDelete(false);
        onDeleted();
      },
      onError: (err) => {
        setConfirmDelete(false);
        setSaveError(err instanceof Error ? err.message : "Delete failed");
      },
    });
  }

  if (mode === "edit" && templateId === null) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">
        Select a template
      </div>
    );
  }
  if (mode === "edit" && isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">
        Loading…
      </div>
    );
  }
  if (mode === "edit" && error) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-danger" role="alert">
        {error.message}
      </div>
    );
  }

  // Pass the in-memory HTML to the preview so users see unsaved edits live.
  // For create mode (no saved template id yet) we can't render via
  // /render-preview, so the preview pane just shows a hint.
  const previewTemplateId = mode === "edit" ? templateId : null;

  return (
    <div className="grid h-full grid-rows-[1fr_auto]">
      <div className="grid grid-cols-1 gap-4 overflow-auto p-card lg:grid-cols-[2fr_1fr]">
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name" id="et-name">
              <Input
                id="et-name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                required
              />
            </Field>
            <Field label="Slug" id="et-slug">
              <Input
                id="et-slug"
                value={form.slug}
                onChange={(e) => set("slug", e.target.value)}
                disabled={mode === "edit"}
                placeholder="snake_case_unique"
                required
              />
            </Field>
            <Field label="Type" id="et-type">
              <select
                id="et-type"
                value={form.email_type}
                onChange={(e) => set("email_type", e.target.value)}
                className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
              >
                {EMAIL_TYPES.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Category" id="et-category">
              <Input
                id="et-category"
                value={form.category}
                onChange={(e) => set("category", e.target.value)}
                placeholder="Optional grouping label"
              />
            </Field>
          </div>

          <Field label="Subject template" id="et-subject">
            <Input
              id="et-subject"
              value={form.subject_template}
              onChange={(e) => set("subject_template", e.target.value)}
              placeholder="Hi {{first_name}}, your order is ready"
            />
          </Field>

          <Field
            label="Required variables (comma-separated)"
            id="et-vars"
          >
            <Input
              id="et-vars"
              value={variablesText}
              onChange={(e) => setVariablesText(e.target.value)}
              placeholder="first_name, company_name"
            />
          </Field>

          <label className="flex items-center gap-2 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => set("is_active", e.target.checked)}
              className="rounded border-border"
            />
            Active (uncheck to hide from broadcast template pickers)
          </label>

          <details className="rounded-md border border-border bg-card/40">
            <summary className="cursor-pointer select-none px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-text-muted">
              Advanced — edit HTML
            </summary>
            <div className="p-2">
              <textarea
                id="et-html"
                value={form.html_content}
                onChange={(e) => set("html_content", e.target.value)}
                rows={14}
                className="w-full rounded-md border border-border bg-card p-2 font-mono text-xs text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                placeholder="<p>Hi {{first_name}}, ...</p>"
              />
              <p className="mt-1 text-[10px] text-text-muted">
                Edits here update the live preview before you save. Save to persist.
              </p>
            </div>
          </details>

          <div>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
              Sample variable values
            </h2>
            {effectiveSpec === null ? (
              <p className="text-xs text-text-muted">
                Add variable names in the field above to drive the preview.
              </p>
            ) : (
              <EmailVariablesForm
                spec={effectiveSpec}
                values={previewVars}
                onChange={setPreviewVars}
                mode="studio"
              />
            )}
          </div>

          {saveError && (
            <p role="alert" className="text-sm text-danger">{saveError}</p>
          )}
        </form>

        <aside className="flex flex-col gap-2">
          {previewTemplateId !== null ? (
            <EmailRenderPreview
              templateId={previewTemplateId}
              variables={previewVars}
              htmlContentOverride={form.html_content || null}
              subjectTemplateOverride={form.subject_template || null}
            />
          ) : (
            <div className="flex h-full items-center justify-center rounded-md border border-dashed border-border bg-card/40 p-card text-center text-xs text-text-muted">
              Save the template to see a rendered preview. The render preview
              uses the saved Jinja shell layout and can't run on an unsaved
              template id.
            </div>
          )}
        </aside>
      </div>

      <footer className="flex items-center justify-between border-t border-border bg-card/40 px-card py-2">
        <div>
          {mode === "edit" && loaded && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete"}
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {(createMutation.isPending || saveMutation.isPending) && (
            <span className="text-xs text-text-muted">Saving…</span>
          )}
          <Button type="submit" onClick={handleSubmit} size="sm">
            {mode === "create" ? "Create" : "Save changes"}
          </Button>
        </div>
      </footer>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete email template?"
        description="This template will be permanently removed. Broadcasts that already used this slug keep their record (we don't touch sent history)."
        confirmLabel="Delete"
        destructive
        isPending={deleteMutation.isPending}
        onConfirm={performDelete}
      />
    </div>
  );
}

function Field({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </Label>
      {children}
    </div>
  );
}

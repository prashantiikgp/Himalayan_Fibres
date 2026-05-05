/**
 * <EmailTemplateEditor> — right panel of /email-templates.
 *
 * Email templates: name, slug (immutable post-create), subject_template,
 * html_content (textarea + iframe HTML preview), email_type, category,
 * required_variables (comma list), is_active.
 *
 * No Meta-style immutability — saving edits in place. No phone preview;
 * the iframe renders the actual HTML so you see what subscribers see.
 */

import { useEffect, useState, type FormEvent } from "react";
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
} from "@/api/email_templates";

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
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const createMutation = useCreateEmailTemplate();
  const saveMutation = useSaveEmailTemplate();
  const deleteMutation = useDeleteEmailTemplate();

  useEffect(() => {
    if (mode === "create") {
      setForm({ ...EMPTY });
      setVariablesText("");
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
      setSaveError(null);
    }
  }, [mode, loaded]);

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
      // slug + name immutable on save in this version (Meta-style discipline);
      // could relax later. Re-send slug for parity but the backend ignores it.
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

          <Field label="HTML body" id="et-html">
            <textarea
              id="et-html"
              value={form.html_content}
              onChange={(e) => set("html_content", e.target.value)}
              rows={14}
              className="rounded-md border border-border bg-card p-2 font-mono text-xs text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              placeholder="<p>Hi {{first_name}}, ...</p>"
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

          {saveError && (
            <p role="alert" className="text-sm text-danger">{saveError}</p>
          )}
        </form>

        <aside className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Preview (raw HTML)
          </h3>
          <iframe
            title="Email preview"
            className="h-[600px] w-full rounded-md border border-border bg-white"
            srcDoc={form.html_content || "<p style='color:#999;font-family:sans-serif;padding:24px'>(empty body)</p>"}
            sandbox=""
          />
          <p className="text-[10px] text-text-muted">
            Variables like <code>{"{{first_name}}"}</code> render literally
            in this preview. Substitution happens at send time, per recipient.
          </p>
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

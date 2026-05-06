/**
 * <TemplateEditor> — center panel of Template Studio.
 *
 * Loads the selected template (or the "New draft" form) and provides
 * inline editing for name, language, category, header, body, footer,
 * and buttons. Submit-to-Meta lands in Phase 4.1b; this commit only
 * exercises the create + save (with clone-on-edit) + delete paths.
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useCreateTemplate,
  useDeleteTemplate,
  useHeaderImages,
  useSaveTemplate,
  useSubmitTemplate,
  useWaTemplate,
  type TemplateUpsert,
  type WATemplateOut,
} from "@/api/wa";
import { ApprovedBanner } from "./ApprovedBanner";
import { ButtonsEditor, type WAButton } from "./ButtonsEditor";
import { TemplatePreview } from "@/components/wa/TemplatePreview";
import { extractPlaceholders } from "@/lib/wa-template-vars";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";

const CATEGORY_OPTIONS = ["MARKETING", "UTILITY", "AUTHENTICATION"];
const LANGUAGE_OPTIONS = ["en_US", "en_GB", "en", "hi", "hi_IN"];
const HEADER_OPTIONS = [
  { value: "", label: "No header" },
  { value: "TEXT", label: "Text" },
  { value: "IMAGE", label: "Image" },
  { value: "DOCUMENT", label: "Document" },
  { value: "VIDEO", label: "Video" },
];

type EditorMode = "create" | "edit";

const EMPTY_FORM: TemplateUpsert & { name: string } = {
  name: "",
  language: "en_US",
  category: "MARKETING",
  body_text: "",
  header_format: null,
  header_text: null,
  header_asset_url: null,
  footer_text: null,
  buttons: [],
};

export function TemplateEditor({
  templateId,
  mode,
  onCreated,
  onDeleted,
}: {
  templateId: number | null;
  mode: EditorMode;
  /** Called with the new template id after a create / clone-on-edit save. */
  onCreated: (id: number) => void;
  /** Called after a successful delete. */
  onDeleted: () => void;
}) {
  const { data: loaded, isLoading, error } = useWaTemplate(
    mode === "edit" ? templateId : null,
  );
  const [form, setForm] = useState<TemplateUpsert & { name: string }>(EMPTY_FORM);
  const [saveError, setSaveError] = useState<string | null>(null);

  const createMutation = useCreateTemplate();
  const saveMutation = useSaveTemplate();
  const deleteMutation = useDeleteTemplate();
  const submitMutation = useSubmitTemplate();
  const { data: headerImagesData } = useHeaderImages();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);

  // Variable values for the preview pane. Studio has no contact in
  // scope (D4 decision: blank, not pre-filled from Meta examples), so
  // these start empty and the input renders `{{varName}}` as a hint.
  const [headerVars, setHeaderVars] = useState<Record<string, string>>({});
  const [bodyVars, setBodyVars] = useState<Record<string, string>>({});

  const headerVarNames = useMemo(
    () => extractPlaceholders(form.header_text ?? ""),
    [form.header_text],
  );
  const bodyVarNames = useMemo(
    () => extractPlaceholders(form.body_text ?? ""),
    [form.body_text],
  );

  // Hydrate the form when the loaded template arrives or mode changes.
  // Variable values reset alongside the form so picks don't carry over
  // when switching between templates.
  useEffect(() => {
    if (mode === "create") {
      setForm({ ...EMPTY_FORM });
      setHeaderVars({});
      setBodyVars({});
      setSaveError(null);
      return;
    }
    if (loaded) {
      setForm({
        name: loaded.name,
        language: loaded.language,
        category: loaded.category ?? "MARKETING",
        body_text: loaded.body_text,
        header_format: loaded.header_format,
        header_text: loaded.header_text,
        header_asset_url: loaded.header_asset_url,
        footer_text: loaded.footer_text,
        buttons: loaded.buttons,
      });
      setHeaderVars({});
      setBodyVars({});
      setSaveError(null);
    }
  }, [mode, loaded]);

  const isImmutable =
    !!loaded && (!loaded.is_draft || (loaded.status && loaded.status.toUpperCase() !== "DRAFT"));

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaveError(null);
    if (mode === "create") {
      if (!form.name.trim()) {
        setSaveError("Name is required.");
        return;
      }
      createMutation.mutate(form, {
        onSuccess: (t) => onCreated(t.id),
        onError: (err) =>
          setSaveError(err instanceof Error ? err.message : "Create failed"),
      });
    } else if (templateId !== null) {
      const payload: TemplateUpsert = { ...form };
      // Name is immutable post-create; don't send it on save.
      delete (payload as { name?: string }).name;
      saveMutation.mutate(
        { id: templateId, body: payload },
        {
          onSuccess: (t: WATemplateOut) => {
            // Clone-on-edit returns a new row id; switch to it.
            if (t.id !== templateId) onCreated(t.id);
          },
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

  function performSubmitToMeta() {
    if (templateId === null) return;
    setSaveError(null);
    submitMutation.mutate(templateId, {
      onSuccess: () => setConfirmSubmit(false),
      onError: (err) => {
        setConfirmSubmit(false);
        setSaveError(err instanceof Error ? err.message : "Submit failed");
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
          {isImmutable && <ApprovedBanner name={form.name} />}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Name" id="tpl-name">
              <Input
                id="tpl-name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                disabled={mode === "edit"}
                required
              />
            </Field>
            <Field label="Language" id="tpl-language">
              <Select
                id="tpl-language"
                value={form.language ?? "en_US"}
                onChange={(v) => set("language", v)}
                options={LANGUAGE_OPTIONS}
              />
            </Field>
            <Field label="Category" id="tpl-category">
              <Select
                id="tpl-category"
                value={form.category ?? "MARKETING"}
                onChange={(v) => set("category", v)}
                options={CATEGORY_OPTIONS}
              />
            </Field>
            <Field label="Header" id="tpl-header-format">
              <select
                id="tpl-header-format"
                value={form.header_format ?? ""}
                onChange={(e) => set("header_format", e.target.value || null)}
                className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
              >
                {HEADER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {form.header_format === "TEXT" && (
            <Field label="Header text" id="tpl-header-text">
              <Input
                id="tpl-header-text"
                value={form.header_text ?? ""}
                onChange={(e) => set("header_text", e.target.value)}
                maxLength={60}
              />
            </Field>
          )}
          {form.header_format && form.header_format !== "TEXT" && (
            <Field label={`${form.header_format} URL`} id="tpl-header-url">
              <div className="flex flex-col gap-1.5">
                <Input
                  id="tpl-header-url"
                  value={form.header_asset_url ?? ""}
                  onChange={(e) => set("header_asset_url", e.target.value)}
                  placeholder="https://… (paste a Supabase URL or pick from the library below)"
                />
                {/* Phase 10.3: dropdown of locally-committed images. */}
                {headerImagesData && headerImagesData.images.length > 0 && (
                  <div className="flex items-center gap-2">
                    <Label
                      htmlFor="tpl-header-library"
                      className="text-[11px] text-text-muted"
                    >
                      From library:
                    </Label>
                    <select
                      id="tpl-header-library"
                      value=""
                      onChange={(e) => {
                        if (e.target.value) {
                          set("header_asset_url", e.target.value);
                          e.target.value = "";  // reset so re-pick works
                        }
                      }}
                      className="h-8 flex-1 rounded-md border border-border bg-card px-2 text-xs text-text"
                    >
                      <option value="">— Pick from {headerImagesData.images.length} image{headerImagesData.images.length === 1 ? "" : "s"} —</option>
                      {headerImagesData.images.map((img) => (
                        <option key={img.url} value={img.url}>
                          {img.filename} ({Math.round(img.size_bytes / 1024)}kb)
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <p className="text-[10px] text-text-subtle">
                  Tip: drop new images into{" "}
                  <code>hf_dashboard/static/wa_template_headers/</code> and
                  redeploy to add them to the library. Supabase URLs from
                  the existing <code>wa-template-images</code> bucket work too.
                </p>
              </div>
            </Field>
          )}

          <Field label="Body" id="tpl-body">
            <textarea
              id="tpl-body"
              value={form.body_text ?? ""}
              onChange={(e) => set("body_text", e.target.value)}
              rows={6}
              className="rounded-md border border-border bg-card p-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              placeholder="Use {{1}}, {{2}} for positional variables, or {{name}} for named."
            />
          </Field>

          <Field label="Footer" id="tpl-footer">
            <Input
              id="tpl-footer"
              value={form.footer_text ?? ""}
              onChange={(e) => set("footer_text", e.target.value)}
              maxLength={60}
              placeholder="Optional small print"
            />
          </Field>

          {/* Phase 10.4: button editor with presets. Buttons render
              live in the phone preview via TemplatePreview. */}
          <ButtonsEditor
            buttons={(form.buttons as WAButton[] | undefined) ?? []}
            onChange={(next) => set("buttons", next)}
          />

          {saveError && (
            <p role="alert" className="text-sm text-danger">{saveError}</p>
          )}
        </form>

        <aside className="flex flex-col gap-3">
          <TemplatePreview
            template={{
              header_format: form.header_format,
              header_text: form.header_text,
              header_asset_url: form.header_asset_url,
              body_text: form.body_text,
              footer_text: form.footer_text,
              buttons: form.buttons,
            }}
            headerVariables={headerVars}
            bodyVariables={bodyVars}
            headerVarNames={headerVarNames}
            bodyVarNames={bodyVarNames}
            onHeaderVarsChange={setHeaderVars}
            onBodyVarsChange={setBodyVars}
            style="phone"
            inputIdPrefix="studio"
          />
        </aside>
      </div>

      <footer className="flex items-center justify-between border-t border-border bg-card/40 px-card py-2">
        <div className="flex items-center gap-2">
          {mode === "edit" && loaded && loaded.is_draft && !loaded.status && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete draft"}
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {createMutation.isPending || saveMutation.isPending ? (
            <span className="text-xs text-text-muted">Saving…</span>
          ) : null}
          <Button type="submit" onClick={handleSubmit} size="sm" variant="outline">
            {mode === "create" ? "Create draft" : isImmutable ? "Save as new draft" : "Save changes"}
          </Button>
          {/* Submit-to-Meta only when this is a saved DRAFT (no status). */}
          {mode === "edit" && loaded && loaded.is_draft && !loaded.status && (
            <Button
              type="button"
              size="sm"
              onClick={() => setConfirmSubmit(true)}
              disabled={submitMutation.isPending}
            >
              {submitMutation.isPending ? "Submitting…" : "Submit to Meta"}
            </Button>
          )}
        </div>
      </footer>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete draft?"
        description="This template will be permanently removed. Submitted templates are immutable; this only works on drafts."
        confirmLabel="Delete"
        destructive
        isPending={deleteMutation.isPending}
        onConfirm={performDelete}
      />
      <ConfirmDialog
        open={confirmSubmit}
        onOpenChange={setConfirmSubmit}
        title="Submit to Meta for approval?"
        description="Submitted templates are immutable. Further edits will create a clone (e.g. <name>_v2). Meta usually approves within a few minutes; check the Sync button to refresh status."
        confirmLabel="Submit"
        isPending={submitMutation.isPending}
        onConfirm={performSubmitToMeta}
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

function Select({
  id,
  value,
  onChange,
  options,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

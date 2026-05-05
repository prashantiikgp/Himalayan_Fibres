/**
 * <WATemplatesPage> — entry component for /wa-templates.
 *
 * Phase 4.1a (this commit) ships the Studio: list + editor with create
 * / save (clone-on-edit) / delete. Submit-to-Meta + Sync-from-Meta
 * land in Phase 4.1b.
 */

import { useSearchParams } from "react-router-dom";
import { configLoader } from "@/loaders/configLoader";
import { TemplateList } from "./components/TemplateList";
import { TemplateEditor } from "./components/TemplateEditor";

export function WATemplatesPage() {
  const cfg = configLoader.getPage("wa_templates");
  const [params, setParams] = useSearchParams();
  const idParam = params.get("id");
  const isCreate = idParam === "new";
  const selectedId =
    !isCreate && idParam !== null && /^\d+$/.test(idParam) ? Number(idParam) : null;

  function setSelected(id: number) {
    const next = new URLSearchParams(params);
    next.set("id", String(id));
    setParams(next, { replace: true });
  }

  function startCreate() {
    const next = new URLSearchParams(params);
    next.set("id", "new");
    setParams(next, { replace: true });
  }

  function clearSelection() {
    const next = new URLSearchParams(params);
    next.delete("id");
    setParams(next, { replace: true });
  }

  return (
    <div className="grid h-[calc(100vh-56px)] grid-cols-[minmax(280px,1fr)_minmax(420px,3fr)] gap-2 p-2">
      <section
        aria-label="Templates list"
        className="overflow-hidden rounded-lg border border-border bg-card/40"
      >
        <TemplateList
          selectedId={selectedId}
          onSelect={setSelected}
          onCreateNew={startCreate}
        />
      </section>

      <section
        aria-label="Editor"
        className="overflow-hidden rounded-lg border border-border bg-card/40"
      >
        {isCreate ? (
          <TemplateEditor
            templateId={null}
            mode="create"
            onCreated={setSelected}
            onDeleted={clearSelection}
          />
        ) : (
          <TemplateEditor
            templateId={selectedId}
            mode="edit"
            onCreated={setSelected}
            onDeleted={clearSelection}
          />
        )}
      </section>

      {/* page title used as a screenreader heading; visually the panels suffice */}
      <h1 className="sr-only">{cfg.page.title}</h1>
    </div>
  );
}

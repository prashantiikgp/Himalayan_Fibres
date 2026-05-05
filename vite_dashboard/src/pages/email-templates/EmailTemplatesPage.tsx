/**
 * <EmailTemplatesPage> — entry component for /email-templates (Phase 6.4).
 */

import { useSearchParams } from "react-router-dom";
import { configLoader } from "@/loaders/configLoader";
import { HowToUse } from "@/components/layout/HowToUse";
import { EmailTemplateList } from "./components/EmailTemplateList";
import { EmailTemplateEditor } from "./components/EmailTemplateEditor";

export function EmailTemplatesPage() {
  const cfg = configLoader.getPage("email_templates");
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
    <div className="flex flex-col gap-2 p-2">
      <HowToUse pageTitle={cfg.page.title} howTo={cfg.page.how_to_use} />

      <div className="grid h-[calc(100vh-180px)] grid-cols-[minmax(280px,1fr)_minmax(420px,3fr)] gap-2">
        <section
          aria-label="Email templates list"
          className="overflow-hidden rounded-lg border border-border bg-card/40"
        >
          <EmailTemplateList
            selectedId={selectedId}
            onSelect={setSelected}
            onCreateNew={startCreate}
          />
        </section>

        <section
          aria-label="Email template editor"
          className="overflow-hidden rounded-lg border border-border bg-card/40"
        >
          {isCreate ? (
            <EmailTemplateEditor
              templateId={null}
              mode="create"
              onCreated={setSelected}
              onDeleted={clearSelection}
            />
          ) : (
            <EmailTemplateEditor
              templateId={selectedId}
              mode="edit"
              onCreated={setSelected}
              onDeleted={clearSelection}
            />
          )}
        </section>
      </div>
    </div>
  );
}

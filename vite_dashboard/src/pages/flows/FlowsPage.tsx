/**
 * <FlowsPage> — entry component for /flows.
 *
 * Phase 5.0 ships read-only: list flows, click a row to see its recent
 * runs. Phase 5.1+ will add Start / Pause / Cancel and the steps editor.
 */

import { configLoader } from "@/loaders/configLoader";
import { HowToUse } from "@/components/layout/HowToUse";
import { FlowsTable } from "./components/FlowsTable";

export function FlowsPage() {
  const cfg = configLoader.getPage("flows");
  return (
    <div className="flex flex-col p-2">
      <HowToUse pageTitle={cfg.page.title} howTo={cfg.page.how_to_use} />
      <FlowsTable />
    </div>
  );
}

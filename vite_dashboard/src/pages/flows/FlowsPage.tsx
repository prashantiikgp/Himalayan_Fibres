/**
 * <FlowsPage> — entry component for /flows.
 *
 * Phase 5.0 ships read-only: list flows, click a row to see its recent
 * runs. Phase 5.1+ will add Start / Pause / Cancel and the steps editor.
 */

import { FlowsTable } from "./components/FlowsTable";

export function FlowsPage() {
  return (
    <div className="p-2">
      <FlowsTable />
    </div>
  );
}

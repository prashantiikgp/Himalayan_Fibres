/**
 * <BroadcastsPage> — entry component for /broadcasts.
 *
 * As of Phase 3.1b.3 all three tabs are functional:
 *   - Compose: WhatsApp send (sync) + Email queue (async via JobStore)
 *   - History: unified WA + Email list (B6 fix)
 *   - Performance: per-broadcast KPIs + paginated recipient table (B16 fix)
 */

import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { configLoader } from "@/loaders/configLoader";
import { ComposeTab } from "./components/ComposeTab";
import { HistoryTab } from "./components/HistoryTab";
import { PerformanceTab } from "./components/PerformanceTab";

const TAB_VALUES = ["compose", "history", "performance"] as const;
type TabValue = (typeof TAB_VALUES)[number];

export function BroadcastsPage() {
  const cfg = configLoader.getPage("broadcasts");
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const active: TabValue =
    raw && (TAB_VALUES as readonly string[]).includes(raw) ? (raw as TabValue) : "compose";

  function setTab(v: string) {
    const next = new URLSearchParams(params);
    next.set("tab", v);
    setParams(next, { replace: true });
  }

  return (
    <div className="flex flex-col gap-3 p-2">
      <header className="px-card pt-card">
        <h1 className="text-lg font-semibold text-text">{cfg.page.title}</h1>
        {cfg.page.subtitle && (
          <p className="text-xs text-text-muted">{cfg.page.subtitle}</p>
        )}
      </header>

      <Tabs value={active} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="compose">Compose</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="compose">
          <ComposeTab />
        </TabsContent>

        <TabsContent value="history">
          <HistoryTab />
        </TabsContent>

        <TabsContent value="performance">
          <PerformanceTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

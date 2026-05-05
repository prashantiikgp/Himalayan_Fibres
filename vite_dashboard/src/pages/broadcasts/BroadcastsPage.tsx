/**
 * <BroadcastsPage> — entry component for /broadcasts.
 *
 * Phase 3.0 (this commit) ships the **History tab** functional. Compose
 * + Performance ship in Phase 3.1+.
 */

import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { configLoader } from "@/loaders/configLoader";
import { HistoryTab } from "./components/HistoryTab";

const TAB_VALUES = ["compose", "history", "performance"] as const;
type TabValue = (typeof TAB_VALUES)[number];

export function BroadcastsPage() {
  const cfg = configLoader.getPage("broadcasts");
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const active: TabValue =
    raw && (TAB_VALUES as readonly string[]).includes(raw) ? (raw as TabValue) : "history";

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
          <ComingSoon
            phase="3.1"
            text="Compose tab — channel toggle, recipient picker, audience funnel (B3 fix), live cost estimate, send confirm dialog (B10 fix)."
          />
        </TabsContent>

        <TabsContent value="history">
          <HistoryTab />
        </TabsContent>

        <TabsContent value="performance">
          <ComingSoon
            phase="3.2"
            text="Performance tab — per-broadcast KPIs + paginated recipient table (B16 fix: no more 100-row silent cap)."
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ComingSoon({ phase, text }: { phase: string; text: string }) {
  return (
    <div className="m-card rounded-lg border border-dashed border-border bg-card/40 p-card text-sm text-text-muted">
      <p className="mb-1 font-semibold text-text">Phase {phase} — coming soon</p>
      <p>{text}</p>
    </div>
  );
}

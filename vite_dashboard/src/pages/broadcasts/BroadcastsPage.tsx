/**
 * <BroadcastsPage> — Compose / History / Performance for one or both channels.
 *
 * Phase 6.3 made channel-locking explicit. Two wrapper routes consume
 * this with `channel` set:
 *   - /wa-broadcasts → channel="whatsapp"
 *   - /email-broadcasts → channel="email"
 *
 * The legacy /broadcasts route mounts this without `channel`, keeping
 * the URL-driven channel toggle in Compose for any saved bookmarks.
 * It redirects to /wa-broadcasts in routes/index.tsx as the default
 * landing.
 */

import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { configLoader } from "@/loaders/configLoader";
import { HowToUse } from "@/components/layout/HowToUse";
import type { BroadcastChannel } from "@/api/broadcasts";
import { ComposeTab } from "./components/ComposeTab";
import { HistoryTab } from "./components/HistoryTab";
import { PerformanceTab } from "./components/PerformanceTab";

const TAB_VALUES = ["compose", "history", "performance"] as const;
type TabValue = (typeof TAB_VALUES)[number];

export function BroadcastsPage({
  channel,
  pageId = "broadcasts",
}: {
  channel?: BroadcastChannel;
  /** Which page YAML to read (broadcasts / wa_broadcasts / email_broadcasts).
   * Defaults to the unified config for back-compat. */
  pageId?: "broadcasts" | "wa_broadcasts" | "email_broadcasts";
} = {}) {
  const cfg = configLoader.getPage(pageId);
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
      <HowToUse pageTitle={cfg.page.title} howTo={cfg.page.how_to_use} />

      <Tabs value={active} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="compose">Compose</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="compose">
          <ComposeTab lockedChannel={channel} />
        </TabsContent>

        <TabsContent value="history">
          <HistoryTab lockedChannel={channel} />
        </TabsContent>

        <TabsContent value="performance">
          <PerformanceTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

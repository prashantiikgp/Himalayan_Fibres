/**
 * Home page — Phase 0 fully functional.
 *
 * Reads layout from config/pages/home.yml via pageEngine, KPI definitions
 * from config/shared/kpi.yml via kpiEngine, and runtime data from
 * /api/v2/dashboard/home.
 *
 * Production-ready: real data, real components, no placeholders.
 */

import { useHomeData } from "@/api/dashboard";
import { pageEngine } from "@/engines/pageEngine";
import { KpiRow } from "@/components/kpi/KpiRow";
import { Card } from "@/components/ui/card";
import { StatusStrip } from "./components/StatusStrip";
import { LifecycleBars } from "./components/LifecycleBars";
import { ActivityFeed } from "./components/ActivityFeed";
import { STRINGS } from "@/lib/strings";

export function HomePage() {
  const cfg = pageEngine.getConfig("home");
  const meta = pageEngine.getMeta("home");
  const { data, isLoading, error } = useHomeData();

  return (
    <div className="flex flex-col gap-section" style={pageEngine.getStyleVars("home")}>
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-text">{meta.title}</h1>
        <p className="text-sm text-text-muted">{meta.subtitle}</p>
      </header>

      {cfg.page.sections.status_strip.enabled && <StatusStrip />}

      {error && (
        <Card className="border-danger/40 px-4 py-3 text-sm text-danger" role="alert">
          {STRINGS.errors.unknown}
        </Card>
      )}

      {isLoading && (
        <Card className="px-4 py-6 text-center text-sm text-text-muted">
          {STRINGS.table.loading}
        </Card>
      )}

      {data && (
        <>
          {cfg.page.sections.kpi_rows.map((row, idx) => (
            <KpiRow
              key={idx}
              ids={row.ids}
              data={data as unknown as Record<string, number | undefined>}
            />
          ))}

          <div className="grid grid-cols-1 gap-section lg:grid-cols-3">
            <div className="lg:col-span-2">
              <LifecycleBars
                title={cfg.page.sections.lifecycle.title}
                entries={data.lifecycle}
                total={data.total}
              />
            </div>
            <ActivityFeed
              title={cfg.page.sections.activity.title}
              entries={data.activity.slice(0, cfg.page.sections.activity.limit)}
            />
          </div>
        </>
      )}
    </div>
  );
}

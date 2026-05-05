/**
 * <KpiRow> — a horizontal row of <KpiCard>s. Driven by KPI ids from a page YAML.
 */

import { kpiEngine } from "@/engines/kpiEngine";
import { KpiCard } from "./KpiCard";
import { cn } from "@/lib/utils";

export function KpiRow({
  ids,
  data,
  className,
}: {
  ids: readonly string[];
  data: Record<string, number | undefined>;
  className?: string;
}) {
  const tiles = kpiEngine.hydrate(ids, data);
  return (
    <div className={cn("grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5", className)}>
      {tiles.map((tile) => (
        <KpiCard key={tile.id} label={tile.label} value={tile.value} color={tile.color} />
      ))}
    </div>
  );
}

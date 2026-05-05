/**
 * <LifecycleBars> — horizontal progress bars by lifecycle stage.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { formatNumber } from "@/lib/format";

export type LifecycleEntry = {
  id: string;
  label: string;
  icon: string;
  color: string;
  count: number;
};

export function LifecycleBars({
  title,
  entries,
  total,
}: {
  title: string;
  entries: LifecycleEntry[];
  total: number;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {entries.map((e) => {
          const pct = total > 0 ? (e.count / total) * 100 : 0;
          return (
            <div key={e.id} className="flex items-center gap-3 text-xs">
              <span className="min-w-[110px] text-text">
                <span aria-hidden className="mr-1">
                  {e.icon}
                </span>
                {e.label}
              </span>
              <div
                className="h-2 flex-1 overflow-hidden rounded-full bg-card"
                role="progressbar"
                aria-valuenow={Math.round(pct)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${e.label}: ${formatNumber(e.count)} contacts`}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, background: e.color }}
                />
              </div>
              <span className="min-w-[50px] text-right font-medium text-text">
                {formatNumber(e.count)}
              </span>
              <span className="min-w-[40px] text-right text-text-muted">{pct.toFixed(0)}%</span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

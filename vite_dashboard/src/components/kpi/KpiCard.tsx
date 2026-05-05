/**
 * <KpiCard> — single metric tile. Consumed by <KpiRow>.
 */

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type KpiCardProps = {
  label: string;
  value: string;
  color?: string;
  className?: string;
};

export function KpiCard({ label, value, color, className }: KpiCardProps) {
  return (
    <Card className={cn("flex flex-col px-4 py-3", className)}>
      <div className="text-2xl font-bold leading-none" style={color ? { color } : undefined}>
        {value}
      </div>
      <div className="mt-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </div>
    </Card>
  );
}

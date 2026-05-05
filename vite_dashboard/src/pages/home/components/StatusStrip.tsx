/**
 * <StatusStrip> — top of Home page. Email + WhatsApp connection status.
 */

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useSystemStatus } from "@/api/dashboard";
import { STRINGS } from "@/lib/strings";

function Pill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div
      className="flex items-center gap-2 rounded-md border border-border bg-card/40 px-3 py-1.5 text-xs"
      role="status"
    >
      <span
        aria-hidden
        className={cn("h-2 w-2 rounded-full", ok ? "bg-success" : "bg-danger")}
      />
      <span className="text-text">{label}</span>
      <span className="text-text-muted">{ok ? STRINGS.home.statusOk : STRINGS.home.statusMissing}</span>
    </div>
  );
}

export function StatusStrip() {
  const { data, isLoading } = useSystemStatus();
  if (isLoading || !data) {
    return (
      <Card className="flex gap-3 px-4 py-2 text-xs text-text-muted">{STRINGS.table.loading}</Card>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Pill label={STRINGS.home.statusEmail} ok={data.gmail_configured} />
      <Pill label={STRINGS.home.statusWhatsApp} ok={data.wa_configured} />
    </div>
  );
}

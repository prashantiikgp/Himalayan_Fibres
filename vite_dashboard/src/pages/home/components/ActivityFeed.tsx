/**
 * <ActivityFeed> — chronological list of recent EmailSend + WAMessage events.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { formatRelative } from "@/lib/format";
import { STRINGS } from "@/lib/strings";

export type ActivityEntry = {
  timestamp: string;
  kind: "email_sent" | "wa_sent" | "wa_received";
  text: string;
};

const KIND_ICONS: Record<ActivityEntry["kind"], string> = {
  email_sent: "↗",
  wa_sent: "↗",
  wa_received: "↙",
};

export function ActivityFeed({ title, entries }: { title: string; entries: ActivityEntry[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="py-6 text-center text-xs text-text-muted">{STRINGS.home.activityEmpty}</p>
        ) : (
          <ul className="flex flex-col gap-2 text-xs">
            {entries.map((e, idx) => (
              <li key={idx} className="flex items-start gap-3 border-b border-border/40 py-1 last:border-0">
                <span className="min-w-[90px] text-text-muted">
                  {formatRelative(e.timestamp)}
                </span>
                <span aria-hidden className="text-text-muted">
                  {KIND_ICONS[e.kind]}
                </span>
                <span className="flex-1 text-text">{e.text}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

import { Mail, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

export function ChannelBadge({
  channel,
  className,
}: {
  channel: "email" | "whatsapp";
  className?: string;
}) {
  const Icon = channel === "email" ? Mail : MessageSquare;
  const label = channel === "email" ? "Email" : "WA";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border border-border bg-card px-1.5 py-0.5 text-[10px] text-text-muted",
        className,
      )}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {label}
    </span>
  );
}

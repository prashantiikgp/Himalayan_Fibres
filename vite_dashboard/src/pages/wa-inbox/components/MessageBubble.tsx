/**
 * <MessageBubble> — one rendered message in the chat panel.
 */

import type { WAMessageOut } from "@/api/wa";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

export function MessageBubble({ message }: { message: WAMessageOut }) {
  const isOut = message.direction === "out";
  const failed = message.status === "failed" || message.error_code;

  return (
    <div
      className={cn(
        "flex w-full",
        isOut ? "justify-end" : "justify-start",
      )}
    >
      <div
        className={cn(
          "flex max-w-[78%] flex-col gap-1 rounded-lg px-3 py-2 text-sm",
          isOut
            ? "bg-primary text-white"
            : "border border-border bg-card text-text",
          failed && "border-danger",
        )}
      >
        {message.media_type && message.media_path && (
          <img
            src={message.media_path}
            alt={message.media_caption ?? ""}
            className="mb-1 max-h-48 rounded-md object-cover"
          />
        )}
        {message.text && (
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
        )}
        {message.media_caption && !message.text && (
          <p className="whitespace-pre-wrap break-words text-xs italic">
            {message.media_caption}
          </p>
        )}
        <div
          className={cn(
            "flex items-center justify-between gap-2 text-[10px]",
            isOut ? "text-white/70" : "text-text-muted",
          )}
        >
          <span>{formatRelative(message.created_at)}</span>
          <span className="uppercase">{failed ? "failed" : message.status}</span>
        </div>
        {failed && message.error_detail && (
          <p className="text-[10px] text-danger" role="alert">
            {message.error_detail}
          </p>
        )}
      </div>
    </div>
  );
}

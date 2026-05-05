/**
 * <ScheduleSheet> — datetime picker dialog for email broadcast scheduling.
 *
 * Phase 3.1b.2. The scheduler loop in api_v2 fires due rows once per
 * minute; this dialog only sets the scheduled_at field on submit.
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function ScheduleSheet({
  open,
  onOpenChange,
  recipientCount,
  templateName,
  isPending,
  errorMessage,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recipientCount: number;
  templateName: string;
  isPending: boolean;
  errorMessage: string | null;
  onConfirm: (iso: string) => void;
}) {
  // Default 1 hour from now, rounded to the next minute.
  const defaultLocal = (() => {
    const d = new Date(Date.now() + 60 * 60 * 1000);
    d.setSeconds(0, 0);
    // datetime-local needs YYYY-MM-DDTHH:mm in the browser's local TZ.
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  })();
  const [value, setValue] = useState(defaultLocal);

  function handleConfirm() {
    if (!value) return;
    // datetime-local is in the browser's local timezone — convert to ISO.
    const iso = new Date(value).toISOString();
    if (new Date(iso).getTime() <= Date.now()) return;
    onConfirm(iso);
  }

  const isFuture = value ? new Date(value).getTime() > Date.now() : false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Schedule broadcast</DialogTitle>
          <DialogDescription>
            Sending <strong>{recipientCount}</strong> recipient(s) using
            template <code>{templateName || "—"}</code>. The scheduler
            checks every minute and fires due broadcasts within ~60s of
            their scheduled time.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-1">
          <label htmlFor="schedule-datetime" className="text-xs text-text-muted">
            When (local time)
          </label>
          <Input
            id="schedule-datetime"
            type="datetime-local"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          {value && !isFuture && (
            <p className="text-xs text-danger" role="alert">
              Pick a time in the future. Use Send Now to fire immediately.
            </p>
          )}
        </div>

        {errorMessage && (
          <p role="alert" className="text-sm text-danger">{errorMessage}</p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={isPending || !isFuture}
          >
            {isPending ? "Scheduling…" : "Schedule"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

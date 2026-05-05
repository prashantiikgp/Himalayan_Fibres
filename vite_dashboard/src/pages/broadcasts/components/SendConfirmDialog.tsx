/**
 * <SendConfirmDialog> — type-SEND-to-confirm gate for Send Now.
 *
 * **B10 fix lives here.** v1's Send Now and Send Test buttons sit
 * adjacent in a row; one keyboard slip and a real broadcast goes out.
 * v2 requires an explicit recipient + cost recap and a typed
 * confirmation phrase before submitting.
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

const CONFIRM_PHRASE = "SEND";

export function SendConfirmDialog({
  open,
  onOpenChange,
  recipientCount,
  costDisplay,
  segmentLabel,
  templateName,
  isPending,
  errorMessage,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recipientCount: number;
  costDisplay: string;
  segmentLabel: string;
  templateName: string;
  isPending: boolean;
  errorMessage: string | null;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const armed = typed === CONFIRM_PHRASE && !isPending && recipientCount > 0;

  function handleClose(o: boolean) {
    if (!o) setTyped("");
    onOpenChange(o);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send broadcast</DialogTitle>
          <DialogDescription>
            Review before this fires. There's no undo once a WhatsApp
            template starts going out — Meta charges per delivered
            conversation regardless of opt-outs.
          </DialogDescription>
        </DialogHeader>

        <dl className="grid grid-cols-3 gap-2 rounded-md border border-border bg-card/40 p-3 text-sm">
          <Term label="Recipients" value={String(recipientCount)} highlight />
          <Term label="Estimated cost" value={costDisplay} highlight />
          <Term label="Audience" value={segmentLabel} />
          <Term label="Template" value={templateName} className="col-span-3" />
        </dl>

        <div className="flex flex-col gap-1">
          <label htmlFor="confirm-phrase" className="text-xs text-text-muted">
            Type <code className="rounded bg-card px-1 py-0.5 text-xs">{CONFIRM_PHRASE}</code> to
            confirm
          </label>
          <Input
            id="confirm-phrase"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            placeholder={CONFIRM_PHRASE}
          />
        </div>

        {errorMessage && (
          <p role="alert" className="text-sm text-danger">
            {errorMessage}
          </p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleClose(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm} disabled={!armed}>
            {isPending ? "Sending…" : "Send Now"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Term({
  label,
  value,
  highlight,
  className = "",
}: {
  label: string;
  value: string;
  highlight?: boolean;
  className?: string;
}) {
  return (
    <div className={`flex flex-col ${className}`}>
      <dt className="text-[10px] uppercase tracking-wider text-text-muted">{label}</dt>
      <dd className={highlight ? "text-base font-semibold text-text" : "text-text"}>
        {value}
      </dd>
    </div>
  );
}

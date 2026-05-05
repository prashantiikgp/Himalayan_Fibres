/**
 * <SendProgress> — polls a queued broadcast's job status and renders
 * progress + completion state.
 *
 * Phase 3.1b.1 doesn't expose per-recipient progress (would require
 * forking v1's email loop). For now the bar advances 5 → 100 on the
 * server-side `running -> done` transition, and the message field
 * shows v1's final counts.
 */

import { useJobProgress, type JobStatusResponse } from "@/api/broadcasts";
import { cn } from "@/lib/utils";

export function SendProgress({
  jobId,
  recipientCount,
}: {
  jobId: string | null;
  recipientCount: number;
}) {
  const { data, error } = useJobProgress(jobId);
  if (jobId === null) return null;

  if (error) {
    return (
      <div role="alert" className="rounded-md border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
        Failed to fetch job status: {error.message}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-md border border-border bg-card/40 p-3 text-sm text-text-muted">
        Connecting to job…
      </div>
    );
  }

  const isTerminal = data.status === "done" || data.status === "failed";
  return (
    <div className={cn(
      "flex flex-col gap-2 rounded-md border p-3 text-sm",
      data.status === "failed"
        ? "border-danger/40 bg-danger/10 text-danger"
        : data.status === "done"
        ? "border-success/40 bg-success/10 text-success"
        : "border-primary/40 bg-primary/10 text-primary",
    )}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs uppercase tracking-wider">{data.status}</span>
        <span className="text-xs">{data.progress}%</span>
      </div>
      <ProgressBar percent={data.progress} status={data.status} />
      <p className="text-xs">
        {data.message || `Targeting ${recipientCount} recipient${recipientCount === 1 ? "" : "s"}`}
      </p>
      {isTerminal && data.result && (
        <Result data={data} recipientCount={recipientCount} />
      )}
    </div>
  );
}

function ProgressBar({
  percent,
  status,
}: {
  percent: number;
  status: JobStatusResponse["status"];
}) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-card">
      <div
        className={cn(
          "h-full transition-all",
          status === "failed"
            ? "bg-danger"
            : status === "done"
            ? "bg-success"
            : "bg-primary",
        )}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

function Result({
  data,
  recipientCount,
}: {
  data: JobStatusResponse;
  recipientCount: number;
}) {
  const r = data.result ?? {};
  const sent = typeof r.total_sent === "number" ? r.total_sent : null;
  const failed = typeof r.total_failed === "number" ? r.total_failed : null;
  const errors = Array.isArray(r.errors) ? (r.errors as string[]) : [];

  return (
    <div className="text-xs">
      {sent !== null && failed !== null ? (
        <p>
          {sent}/{recipientCount} sent · {failed} failed
        </p>
      ) : null}
      {errors.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer">{errors.length} error(s)</summary>
          <ul className="mt-1 max-h-32 list-disc overflow-auto pl-4">
            {errors.slice(0, 20).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

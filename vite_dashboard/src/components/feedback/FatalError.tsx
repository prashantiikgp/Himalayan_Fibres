/**
 * FatalError — full-page error screen rendered when configLoader.bootstrap()
 * or another irrecoverable boot step fails.
 *
 * Per STANDARDS production-readiness principle: validation errors fail loud.
 * This is the loud part. Don't replace it with a "fall back to defaults" path.
 */

export function FatalError({ error }: { error: Error }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-8">
      <div className="max-w-2xl rounded-lg border border-danger/40 bg-card p-8 shadow-lg">
        <div className="mb-4 flex items-center gap-3">
          <span aria-hidden className="text-3xl">
            ⚠
          </span>
          <h1 className="text-xl font-bold text-danger">Dashboard failed to start</h1>
        </div>
        <p className="mb-4 text-sm text-text-muted">
          {error.name === "ConfigValidationError"
            ? "A YAML configuration file failed validation. The dashboard refuses to start with bad config rather than render with silent fallbacks. Fix the file and reload."
            : "An unrecoverable error occurred during application boot."}
        </p>
        <pre className="overflow-auto rounded-md border border-border bg-bg p-4 text-xs text-text-subtle">
          {error.stack ?? error.message}
        </pre>
        <p className="mt-4 text-xs text-text-muted">
          If this persists, check the browser console and the Sentry dashboard for the full stack
          trace.
        </p>
      </div>
    </div>
  );
}

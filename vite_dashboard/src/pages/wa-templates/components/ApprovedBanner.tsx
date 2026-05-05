/**
 * <ApprovedBanner> — clone-on-edit warning shown above the editor when
 * the loaded template is APPROVED / PENDING / REJECTED.
 *
 * Mirrors v1's studio behavior: saving an approved template doesn't
 * mutate the immutable submitted record — it creates a draft clone
 * `<base>_v2` (or _v3, etc) so the live template keeps working.
 */

export function ApprovedBanner({ name }: { name: string }) {
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-xs text-warning"
    >
      <span className="text-base leading-none" aria-hidden="true">
        🔒
      </span>
      <div className="flex flex-col gap-1">
        <p className="font-semibold">This template is submitted to Meta — saving creates a clone.</p>
        <p>
          The original <code>{name}</code> stays untouched. Saving will create
          a new draft (e.g. <code>{name}_v2</code>) that you can edit and
          re-submit. Submitted templates are immutable.
        </p>
      </div>
    </div>
  );
}

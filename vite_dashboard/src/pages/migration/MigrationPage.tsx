/**
 * MigrationPage — the route component used by every page that hasn't yet
 * been migrated. Reads its own metadata from pageEngine and renders the
 * <MigrationStatusCard> with real v1 deep-links.
 *
 * Per STANDARDS production-readiness principle: this is a real working
 * component, not a placeholder. Once a page is migrated, its route in
 * src/routes/index.tsx swaps from <MigrationPage pageId="..."/> to the
 * actual page component.
 */

import { MigrationStatusCard } from "@/components/layout/MigrationStatusCard";
import { pageEngine } from "@/engines/pageEngine";
import type { PageId } from "@/schemas/pages";

export function MigrationPage({ pageId }: { pageId: PageId }) {
  const meta = pageEngine.getMeta(pageId);
  return (
    <div className="flex flex-col gap-section">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-text">{meta.title}</h1>
        <p className="text-sm text-text-muted">{meta.subtitle}</p>
      </header>
      <MigrationStatusCard
        pageId={pageId}
        pageName={meta.title}
        landedPhase={meta.landed_phase}
      />
    </div>
  );
}

/**
 * <HowToUse> — collapsible page header replacing <h1>title</h1><p>subtitle</p>.
 *
 * Phase 6.2. Each page YAML carries `page.how_to_use.{summary,sections}`,
 * validated by HowToUse in schemas/_common.ts. The summary is a single
 * always-visible line; clicking expands a sectioned step-by-step.
 *
 * Usage:
 *   import { HowToUse } from "@/components/layout/HowToUse";
 *   <HowToUse pageTitle={cfg.page.title} howTo={cfg.page.how_to_use} />
 *
 * Stays uncontrolled — local <details> state is sufficient. URL state
 * would be overkill for an in-page accordion.
 */

import { ChevronDown } from "lucide-react";
import type { HowToUseT } from "@/schemas/_common";

export function HowToUse({
  pageTitle,
  howTo,
}: {
  pageTitle: string;
  howTo: HowToUseT | undefined;
}) {
  if (!howTo) {
    // Backwards-compat: pages that haven't migrated their YAML yet
    // still get a heading.
    return (
      <header className="px-card pt-card">
        <h1 className="text-lg font-semibold text-text">{pageTitle}</h1>
      </header>
    );
  }

  return (
    <header className="px-card pt-card">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-baseline gap-2 [&::-webkit-details-marker]:hidden">
          <h1 className="text-lg font-semibold text-text">{pageTitle}</h1>
          <span className="text-xs text-text-muted">{howTo.summary}</span>
          <ChevronDown
            className="ml-auto h-4 w-4 shrink-0 self-center text-text-muted transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>

        {howTo.sections.length > 0 && (
          <div className="mt-3 flex flex-col gap-3 rounded-lg border border-border bg-card/40 p-card text-sm">
            {howTo.sections.map((s, i) => (
              <section key={i} className="flex flex-col gap-1">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                  {s.title}
                </h2>
                <p className="whitespace-pre-line text-text">{s.body}</p>
              </section>
            ))}
          </div>
        )}
      </details>
    </header>
  );
}

/**
 * <MigrationStatusCard> — production component (not a placeholder) shown on
 * routes whose feature has not yet been migrated to v2.
 *
 * Per STANDARDS production-readiness principle: this replaces the original
 * `<ComingSoon />` stub. It shows the page name, the phase its full feature
 * lands in, and a working "Open in v1 dashboard" link.
 *
 * v1 URL is read from VITE_V1_BASE_URL or defaults to the prod HF Space URL.
 */

import { ExternalLink, Construction } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { STRINGS, tFormat } from "@/lib/strings";

const V1_BASE_URL =
  import.meta.env["VITE_V1_BASE_URL"] ??
  "https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space";

// v1 is a Gradio single-page app — query params don't navigate to a specific
// page (review fix M4). Linking to root + telling the user where to click
// inside v1 is the honest UX.
const V1_NAV_HINT_BY_ID: Record<string, string> = {
  home: "Home tab",
  contacts: "the Contacts tab",
  wa_inbox: "the WhatsApp tab",
  broadcasts: "WhatsApp Broadcasts (or Email Broadcast)",
  wa_templates: "the Template Studio tab",
  flows: "the Flows tab",
};

export function MigrationStatusCard({
  pageId,
  pageName,
  landedPhase,
}: {
  pageId: string;
  pageName: string;
  landedPhase: number;
}) {
  const v1Href = V1_BASE_URL;
  const navHint = V1_NAV_HINT_BY_ID[pageId] ?? "the relevant tab";

  return (
    <div className="mx-auto mt-12 w-full max-w-2xl">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <Construction className="h-6 w-6 text-warning" aria-hidden />
            <div>
              <CardTitle>
                {STRINGS.migrationCard.titlePrefix} Phase {landedPhase}
              </CardTitle>
              <CardDescription>
                {tFormat(STRINGS.migrationCard.body, { pageName })}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <a
              href={v1Href}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`${STRINGS.migrationCard.openV1} (${pageName})`}
            >
              <ExternalLink className="mr-2 h-4 w-4" aria-hidden />
              {STRINGS.migrationCard.openV1}
            </a>
          </Button>
          <p className="mt-2 text-xs text-text-muted">
            Once v1 loads, click <strong>{navHint}</strong> in the left sidebar.
          </p>
          <p className="mt-1 text-xs text-text-muted">{STRINGS.migrationCard.sharedDb}</p>
        </CardContent>
      </Card>
    </div>
  );
}

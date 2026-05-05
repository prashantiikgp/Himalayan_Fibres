/**
 * Page-config schemas — one per route, all in this file for now since they
 * share many primitives. Each page YAML lives at config/pages/<id>.yml.
 *
 * Phase 0 ships the Home schema in full (Home is fully functional in v2 from
 * Phase 0). The other pages have minimum-viable schemas that will expand as
 * each page is migrated in its phase.
 */

import { z } from "zod";
import { CssLength, HowToUse, NonEmptyString, NonNegInt, PosInt } from "./_common";

/** Common page-level metadata that every page YAML carries. */
const PageMeta = z
  .object({
    title: NonEmptyString,
    /** A 1-2 sentence description shown in the page header.
     * Phase 6.2 superseded by `how_to_use.summary`; left optional for
     * back-compat with pages that haven't migrated their YAML yet. */
    subtitle: z.string().default(""),
    /** Phase this page reaches feature-parity in. <MigrationStatusCard> reads this. */
    landed_phase: z.number().int().min(0).max(10),
    /** Phase 6.2 — replaces title+subtitle with a collapsible accordion.
     * Optional during the rollout; pages without it keep the legacy
     * title-only header. */
    how_to_use: HowToUse.optional(),
  })
  .strict();

/* ── Home (Phase 0 — fully functional) ─────────────────────────────────── */

export const HomePageConfig = z
  .object({
    page: PageMeta.extend({
      sections: z
        .object({
          status_strip: z.object({ enabled: z.boolean().default(true) }).strict(),
          kpi_rows: z
            .array(
              z
                .object({
                  /** KPI ids referenced from config/shared/kpi.yml */
                  ids: z.array(NonEmptyString).min(1),
                })
                .strict(),
            )
            .min(1),
          lifecycle: z
            .object({
              title: NonEmptyString,
              limit: PosInt.default(20),
            })
            .strict(),
          activity: z
            .object({
              title: NonEmptyString,
              limit: PosInt.default(20),
            })
            .strict(),
        })
        .strict(),
      styles: z.record(z.string(), CssLength).default({}),
    }).strict(),
  })
  .strict();

export type HomePageConfigT = z.infer<typeof HomePageConfig>;

/* ── Contacts (Phase 1) ─────────────────────────────────────────────────── */

export const ContactsPageConfig = z
  .object({
    page: PageMeta.extend({
      table: z
        .object({
          page_size: PosInt.default(50),
          /** Column ids — concrete column defs live in the table component. */
          columns: z.array(NonEmptyString).min(1),
        })
        .strict(),
      filters: z.array(NonEmptyString).default([]),
      styles: z.record(z.string(), CssLength).default({}),
    }).strict(),
  })
  .strict();

export type ContactsPageConfigT = z.infer<typeof ContactsPageConfig>;

/* ── WA Inbox (Phase 2) ─────────────────────────────────────────────────── */

export const WaInboxPageConfig = z
  .object({
    page: PageMeta.extend({
      panels: z
        .object({
          conversations: z
            .object({
              min_width: NonNegInt,
              search_placeholder: NonEmptyString,
            })
            .strict(),
          chat: z
            .object({
              min_width: NonNegInt,
              compose_placeholder: NonEmptyString,
              window_warning: NonEmptyString,
              new_conv_warning: NonEmptyString,
            })
            .strict(),
          template_sheet: z
            .object({
              title: NonEmptyString,
              send_button_label: NonEmptyString,
            })
            .strict(),
        })
        .strict(),
      styles: z.record(z.string(), CssLength).default({}),
    }).strict(),
  })
  .strict();

export type WaInboxPageConfigT = z.infer<typeof WaInboxPageConfig>;

/* ── Broadcasts (Phase 3) ───────────────────────────────────────────────── */

export const BroadcastsPageConfig = z
  .object({
    page: PageMeta.extend({
      tabs: z
        .array(
          z
            .object({
              id: z.enum(["compose", "history", "performance"]),
              label: NonEmptyString,
            })
            .strict(),
        )
        .min(1),
      styles: z.record(z.string(), CssLength).default({}),
    }).strict(),
  })
  .strict();

export type BroadcastsPageConfigT = z.infer<typeof BroadcastsPageConfig>;

/* ── WA Templates (Phase 4) ─────────────────────────────────────────────── */

export const WaTemplatesPageConfig = z
  .object({
    page: PageMeta.extend({
      list: z
        .object({
          page_size: PosInt.default(20),
        })
        .strict(),
      styles: z.record(z.string(), CssLength).default({}),
    }).strict(),
  })
  .strict();

export type WaTemplatesPageConfigT = z.infer<typeof WaTemplatesPageConfig>;

/* ── Flows (Phase 5) ────────────────────────────────────────────────────── */

export const FlowsPageConfig = z
  .object({
    page: PageMeta.extend({
      runs_limit: PosInt.default(10),
      styles: z.record(z.string(), CssLength).default({}),
    }).strict(),
  })
  .strict();

export type FlowsPageConfigT = z.infer<typeof FlowsPageConfig>;

/* ── Email Templates (Phase 6.4) ───────────────────────────────────────── */

export const EmailTemplatesPageConfig = z
  .object({
    page: PageMeta.strict(),
  })
  .strict();

export type EmailTemplatesPageConfigT = z.infer<typeof EmailTemplatesPageConfig>;

/* ── Send Email (Phase 7.1) ────────────────────────────────────────────── */

export const EmailSendPageConfig = z
  .object({
    page: PageMeta.strict(),
  })
  .strict();

export type EmailSendPageConfigT = z.infer<typeof EmailSendPageConfig>;

/** Map page ID → its config schema. Loader iterates this.
 * Phase 6.3 added wa_broadcasts + email_broadcasts which reuse the
 * BroadcastsPageConfig schema (same shape, different copy).
 * Phase 6.4 added email_templates.
 * Phase 7.1 added email_send. */
export const PAGE_SCHEMAS = {
  home: HomePageConfig,
  contacts: ContactsPageConfig,
  wa_inbox: WaInboxPageConfig,
  broadcasts: BroadcastsPageConfig,
  wa_broadcasts: BroadcastsPageConfig,
  email_broadcasts: BroadcastsPageConfig,
  wa_templates: WaTemplatesPageConfig,
  email_templates: EmailTemplatesPageConfig,
  email_send: EmailSendPageConfig,
  flows: FlowsPageConfig,
} as const;

export type PageId = keyof typeof PAGE_SCHEMAS;
export const PAGE_IDS: readonly PageId[] = Object.keys(PAGE_SCHEMAS) as PageId[];

export type PageConfigByID = {
  home: HomePageConfigT;
  contacts: ContactsPageConfigT;
  wa_inbox: WaInboxPageConfigT;
  broadcasts: BroadcastsPageConfigT;
  wa_broadcasts: BroadcastsPageConfigT;
  email_broadcasts: BroadcastsPageConfigT;
  wa_templates: WaTemplatesPageConfigT;
  email_templates: EmailTemplatesPageConfigT;
  email_send: EmailSendPageConfigT;
  flows: FlowsPageConfigT;
};

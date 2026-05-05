/**
 * Sidebar schema — validates config/dashboard/sidebar.yml.
 *
 * v2 reorganizes the v1 flat list into channel-grouped nav (per audit B11 fix).
 * Structure:
 *
 *   sidebar:
 *     groups:
 *       - id: top
 *         items: [home, contacts]
 *       - id: whatsapp
 *         label: WhatsApp
 *         items: [wa_inbox, broadcasts_wa, wa_templates]
 *       - id: email
 *         label: Email
 *         items: [broadcasts_email, email_analytics]
 *       - id: shared
 *         items: [flows]
 *
 * navigationEngine consumes this and produces React Router routes.
 */

import { z } from "zod";
import { NonEmptyString } from "./_common";

export const NavItem = z
  .object({
    id: NonEmptyString.describe("Page ID — must match a route in routes/index.ts"),
    label: NonEmptyString,
    /** Lucide icon name (e.g. 'Home', 'Users', 'MessageSquare'). */
    icon: NonEmptyString,
    /** Optional URL override; if omitted, route is `/${id}`. */
    path: z.string().optional(),
    /** Phase the page lands in. Used by <MigrationStatusCard>. */
    landed_phase: z.number().int().min(0).max(5),
    /** Channel hint for analytics segmentation. */
    channel: z.enum(["mixed", "email", "whatsapp"]).default("mixed"),
  })
  .strict();

export type NavItemT = z.infer<typeof NavItem>;

export const NavGroup = z
  .object({
    id: NonEmptyString,
    /** Group label shown above the items. Top-level groups (id: 'top') hide the label. */
    label: z.string().default(""),
    items: z.array(NavItem).min(1),
  })
  .strict();

export type NavGroupT = z.infer<typeof NavGroup>;

export const SidebarConfig = z
  .object({
    sidebar: z
      .object({
        groups: z.array(NavGroup).min(1),
      })
      .strict(),
  })
  .strict();

export type SidebarConfigT = z.infer<typeof SidebarConfig>;

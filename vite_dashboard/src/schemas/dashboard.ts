/**
 * Dashboard meta — title, default route, etc.
 */

import { z } from "zod";
import { NonEmptyString } from "./_common";

export const DashboardConfig = z
  .object({
    title: NonEmptyString,
    subtitle: z.string().default(""),
    default_page: NonEmptyString,
  })
  .strict();

export type DashboardConfigT = z.infer<typeof DashboardConfig>;

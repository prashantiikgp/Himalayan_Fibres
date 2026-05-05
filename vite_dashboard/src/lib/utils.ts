/**
 * Shared utilities. Shadcn's `cn()` plus a couple of small helpers.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Combines clsx + tailwind-merge so later utility classes win conflicts. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Type-safe `Object.entries` that preserves key types. */
export function entries<T extends object>(obj: T): [keyof T, T[keyof T]][] {
  return Object.entries(obj) as [keyof T, T[keyof T]][];
}

/** Asserts a value is non-nullish; narrows the type. Throws if not. */
export function assertDefined<T>(value: T | null | undefined, message: string): asserts value is T {
  if (value === null || value === undefined) {
    throw new Error(`assertDefined failed: ${message}`);
  }
}

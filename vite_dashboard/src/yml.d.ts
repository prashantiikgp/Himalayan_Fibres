/**
 * Ambient type declaration for YAML imports.
 *
 * vite-plugin-yaml turns `*.yml` imports into JS objects at build time. TS
 * doesn't know that, so we tell it the import resolves to `unknown` —
 * configLoader.ts then runs Zod validation on the value, which produces
 * the typed result downstream.
 *
 * `unknown` (not `any`) keeps the no-`any` rule from STANDARDS §4 intact.
 */

declare module "*.yml" {
  const content: unknown;
  export default content;
}

declare module "*.yaml" {
  const content: unknown;
  export default content;
}

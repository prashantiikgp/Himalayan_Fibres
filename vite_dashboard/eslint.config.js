import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import jsxA11y from "eslint-plugin-jsx-a11y";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";

export default [
  { ignores: ["dist", "node_modules", "src/api/schema.d.ts", "playwright-report"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      // React/DOM TS types reference React and DOM globals; node config
      // files (vite.config, playwright.config, etc.) reference process.
      // Including all three keeps no-undef from flagging legitimate uses.
      globals: { ...globals.browser, ...globals.node, React: "readonly" },
      parser: tsparser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...tseslint.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      // TS catches undefined identifiers more accurately than eslint's
      // no-undef (which doesn't understand DOM lib types like RequestInit).
      "no-undef": "off",
      // Fast-refresh hint: dev-only optimization, not a correctness rule.
      // Shadcn primitives legitimately co-export Button + buttonVariants.
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/consistent-type-imports": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
];

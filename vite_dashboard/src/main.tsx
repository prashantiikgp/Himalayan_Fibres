/**
 * Application entry point.
 *
 * Boot order (per STANDARDS production-readiness principle):
 *   1. Init Sentry — so any error after this is captured
 *   2. Init analytics
 *   3. Bootstrap configLoader — validates every YAML; throws on bad config
 *   4. Apply theme to :root
 *   5. Mount React with the QueryClientProvider
 *
 * If step 3 throws (bad YAML), we mount <FatalError> instead. Per the
 * production-readiness principle, we never silently fall back to defaults.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { FatalError } from "./components/feedback/FatalError";
import { configLoader } from "./loaders/configLoader";
import { themeEngine } from "./engines/themeEngine";
import { queryClient } from "./lib/queryClient";
import { initSentry, SentryErrorBoundary } from "./lib/sentry";
import { initAnalytics } from "./lib/analytics";
import "./styles/globals.css";

const rootEl = document.getElementById("root");
if (!rootEl) {
  // index.html is missing #root — should be impossible.
  document.body.innerHTML = "<pre>Missing #root element</pre>";
  throw new Error("Missing #root element");
}

const root = createRoot(rootEl);

initSentry();
initAnalytics();

try {
  configLoader.bootstrap();
  themeEngine.applyToDocument();

  root.render(
    <StrictMode>
      <SentryErrorBoundary fallback={({ error }) => <FatalError error={error as Error} />}>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </SentryErrorBoundary>
    </StrictMode>,
  );
} catch (err) {
  console.error("Boot failed:", err);
  root.render(<FatalError error={err instanceof Error ? err : new Error(String(err))} />);
}

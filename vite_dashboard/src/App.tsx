/**
 * App root — renders the router. Wrapped by main.tsx in QueryClientProvider
 * and Sentry.ErrorBoundary.
 */

import { useMemo } from "react";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { buildRoutes } from "@/routes";

export function App() {
  // buildRoutes reads from configLoader, which is bootstrapped before App mounts.
  const router = useMemo(() => createBrowserRouter(buildRoutes()), []);
  return <RouterProvider router={router} />;
}

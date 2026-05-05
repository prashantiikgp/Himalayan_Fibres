/**
 * TanStack Query client — production retry/error policy.
 *
 * Decisions:
 *   - 30s staleTime: most dashboard data is fine to refetch on window focus,
 *     so the cache is short-lived. Per-query overrides are fine.
 *   - 1 retry on network errors only, not on 4xx (no point retrying 401/403).
 *   - On 401, the apiFetch helper redirects to /login; queries don't need to.
 */

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      gcTime: 5 * 60 * 1000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => {
        if (error instanceof ApiError) {
          // Don't retry 4xx — caller will see the error and decide.
          if (error.status >= 400 && error.status < 500) return false;
        }
        return failureCount < 1;
      },
    },
    mutations: {
      retry: false,
    },
  },
});

/** Thrown by apiFetch when the response is non-2xx. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    public readonly url: string,
  ) {
    super(`API ${status} on ${url}: ${body.slice(0, 200)}`);
    this.name = "ApiError";
  }
}

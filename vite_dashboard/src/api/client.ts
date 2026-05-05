/**
 * Typed API client. All fetcher modules under src/api/ use apiFetch.
 *
 * Auth lifecycle (per STANDARDS §1):
 *   - Reads token via getToken()
 *   - On 401, clears token and redirects to /login (handled here, not by callers)
 *   - Throws ApiError with status + body on 4xx/5xx so callers can switch
 */

import { getToken, clearToken } from "@/lib/auth";
import { apiBase } from "@/lib/env";
import { ApiError } from "@/lib/queryClient";

type FetchOpts = RequestInit & { skipAuth?: boolean };

export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const { skipAuth, headers, ...rest } = opts;
  const url = `${apiBase()}${path}`;
  const token = skipAuth ? null : getToken();

  const res = await fetch(url, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers ?? {}),
    },
  });

  if (res.status === 401 && !skipAuth) {
    clearToken();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthenticated", url);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body, url);
  }

  // No-content responses (204) — return an empty object cast to T.
  if (res.status === 204) return {} as T;

  return (await res.json()) as T;
}

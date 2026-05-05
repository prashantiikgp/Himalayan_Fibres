/**
 * useUrlState — sync state into the URL search params so filters survive
 * reload and are shareable. Per STANDARDS production-readiness principle:
 * URL state isn't a nice-to-have, it's a Phase 0 baseline.
 */

import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export function useUrlState() {
  const [params, setParams] = useSearchParams();

  const get = useCallback(
    (key: string, fallback = ""): string => params.get(key) ?? fallback,
    [params],
  );

  const getList = useCallback((key: string): string[] => params.getAll(key), [params]);

  const set = useCallback(
    (updates: Record<string, string | string[] | null | undefined>) => {
      const next = new URLSearchParams(params);
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === undefined || value === "") {
          next.delete(key);
        } else if (Array.isArray(value)) {
          next.delete(key);
          for (const v of value) if (v) next.append(key, v);
        } else {
          next.set(key, value);
        }
      }
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  return useMemo(() => ({ get, getList, set, params }), [get, getList, set, params]);
}

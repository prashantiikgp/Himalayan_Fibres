/**
 * Generic React hooks. Single home so they don't drift.
 */

import { useEffect, useState } from "react";

/**
 * Debounce a value — returns the previous value until `delay` ms have passed
 * without `value` changing. Used by the contacts search input (review fix M5)
 * so each keystroke doesn't fire a new API request.
 */
export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);

  return debounced;
}

/**
 * Bearer-authenticated SSE consumer.
 *
 * Browser EventSource doesn't support custom headers, so we use fetch()
 * + ReadableStream and parse SSE chunks manually. The connection is
 * kept open with auto-reconnect on transient failures, capped to 30s
 * backoff.
 */

import { apiBase } from "./env";
import { clearToken, getToken } from "./auth";

export type SseEvent = {
  event: string;
  data: string;
};

type Handlers = {
  onEvent: (e: SseEvent) => void;
  onError?: (err: Error) => void;
  onOpen?: () => void;
};

/**
 * Open an SSE connection at the given path. Returns a disposer that
 * closes the connection when called.
 */
export function openSseStream(path: string, handlers: Handlers): () => void {
  let cancelled = false;
  let controller: AbortController | null = null;
  let backoff = 1000; // ms

  async function loop() {
    while (!cancelled) {
      controller = new AbortController();
      try {
        const token = getToken();
        const res = await fetch(`${apiBase()}${path}`, {
          method: "GET",
          headers: token
            ? {
                Authorization: `Bearer ${token}`,
                Accept: "text/event-stream",
              }
            : { Accept: "text/event-stream" },
          signal: controller.signal,
        });

        if (res.status === 401) {
          clearToken();
          handlers.onError?.(new Error("Unauthenticated SSE"));
          return;
        }
        if (!res.ok || !res.body) {
          throw new Error(`SSE ${res.status}`);
        }

        handlers.onOpen?.();
        backoff = 1000; // reset on successful connect

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE events are separated by a blank line.
          let sep: number;
          while ((sep = buffer.indexOf("\n\n")) !== -1) {
            const block = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const evt = parseSseBlock(block);
            if (evt) handlers.onEvent(evt);
          }
        }
      } catch (err) {
        if (cancelled) return;
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
      }

      if (cancelled) return;
      // Exponential backoff up to 30s.
      await new Promise((r) => setTimeout(r, backoff));
      backoff = Math.min(backoff * 2, 30_000);
    }
  }

  loop();

  return () => {
    cancelled = true;
    controller?.abort();
  };
}

function parseSseBlock(block: string): SseEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue; // comment / heartbeat
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createReadScope } from "./state";

type Resource<T> = { url: string; data?: T; error: string; loading: boolean };

/** Read-only polling. A response can update only the URL that requested it. */
export function useSocialResource<T>(url: string, initial?: T, merge?: (previous: T, next: T) => T) {
  const [state, setState] = useState<Resource<T>>({ url, data: initial, error: "", loading: !initial });
  const request = useRef<AbortController | null>(null);
  const scope = useRef<ReturnType<typeof createReadScope> | null>(null);

  const refresh = useCallback(async () => {
    const reader = scope.current;
    if (!reader || reader.url !== url) return;
    const ticket = reader.begin();
    if (!reader.accepts(ticket)) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setState(previous => reader.accepts(ticket) ? { url, data: previous.url === url ? previous.data : undefined, error: previous.url === url ? previous.error : "", loading: true } : previous);
    try {
      const response = await fetch(url, { signal: controller.signal, cache: "no-store", credentials: "same-origin" });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.error === "string" ? body.error : "Could not refresh. Try again.");
      if (controller.signal.aborted || !reader.accepts(ticket)) return;
      setState(previous => reader.accepts(ticket) ? { url, data: merge && previous.url === url && previous.data ? merge(previous.data, body as T) : body as T, error: "", loading: false } : previous);
    } catch (error) {
      if (controller.signal.aborted || !reader.accepts(ticket)) return;
      setState(previous => reader.accepts(ticket) ? { url, data: previous.url === url ? previous.data : undefined,
        error: navigator.onLine ? (error instanceof Error ? error.message : "Could not refresh. Try again.") : "You are offline. Your draft is saved in this page.", loading: false } : previous);
    } finally { if (request.current === controller) request.current = null; }
  }, [url, merge]);

  const update = useCallback((change: (previous: T) => T) => {
    if (scope.current?.url !== url) return;
    setState(previous => previous.url === url && previous.data ? { ...previous, data: change(previous.data) } : previous);
  }, [url]);

  useEffect(() => {
    const reader = createReadScope(url);
    scope.current = reader;
    const visibleRefresh = () => {
      if (document.visibilityState === "visible") void refresh();
      else { request.current?.abort(); reader.begin(); }
    };
    visibleRefresh();
    const timer = window.setInterval(() => {
      // Do not abort a slow healthy request every five seconds.
      if (document.visibilityState === "visible" && !request.current) void refresh();
    }, 5000);
    window.addEventListener("focus", visibleRefresh);
    window.addEventListener("online", visibleRefresh);
    document.addEventListener("visibilitychange", visibleRefresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", visibleRefresh);
      window.removeEventListener("online", visibleRefresh);
      document.removeEventListener("visibilitychange", visibleRefresh);
      reader.dispose();
      if (scope.current === reader) { scope.current = null; request.current?.abort(); }
    };
  }, [refresh, url]);

  return { data: state.url === url ? state.data : undefined, error: state.url === url ? state.error : "", loading: state.url !== url || state.loading, refresh, update };
}

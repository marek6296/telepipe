"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

type IdleWindow = Window &
  typeof globalThis & {
    requestIdleCallback?: (
      callback: () => void,
      options?: { timeout: number },
    ) => number;
    cancelIdleCallback?: (id: number) => void;
  };

/**
 * Zahreje dynamické app routy až po vykreslení aktuálnej obrazovky.
 * Jednotlivé requesty sú rozostúpené, aby prednačítanie nikdy nesúťažilo
 * s obsahom, na ktorý používateľ práve čaká.
 */
export function useBackgroundPrefetch(
  routes: readonly string[],
  delay = 450,
  waitForIdle = true,
) {
  const router = useRouter();
  const routeKey = routes.join("\n");

  useEffect(() => {
    const uniqueRoutes = Array.from(new Set(routeKey.split("\n").filter(Boolean)));
    if (uniqueRoutes.length === 0) return;

    const browserWindow = window as IdleWindow;
    const timers: number[] = [];
    let idleId: number | undefined;

    const warmRoutes = () => {
      uniqueRoutes.forEach((href, index) => {
        timers.push(
          window.setTimeout(() => router.prefetch(href), delay + index * 140),
        );
      });
    };

    if (!waitForIdle) {
      timers.push(window.setTimeout(warmRoutes, 0));
    } else if (browserWindow.requestIdleCallback) {
      idleId = browserWindow.requestIdleCallback(warmRoutes, { timeout: 1800 });
    } else {
      timers.push(window.setTimeout(warmRoutes, 700));
    }

    return () => {
      if (idleId !== undefined) browserWindow.cancelIdleCallback?.(idleId);
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [delay, routeKey, router, waitForIdle]);
}

"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";

import { useNotificationStream } from "@/components/app/use-notification-stream";
import type { NotificationRow } from "@/lib/notifications-ui";

/**
 * Na `/locked`: keď Marek žiadosť schváli, stránka sa prepne sama.
 *
 * Nič nevykresľuje. `router.refresh()` prerátá serverový komponent, ten uvidí
 * `plan = free_plus` a presmeruje do `/app` — čiže človek, ktorý na obrazovku
 * pozerá, uvidí odomknutie bez toho, aby čokoľvek stlačil.
 *
 * Zamietnutie refreshuje tiež, aby sa mu rovno ukázal dôvod.
 */
export function LiveUnlock() {
  const router = useRouter();

  const onInsert = useCallback(
    (row: NotificationRow) => {
      if (row.kind === "access_approved" || row.kind === "access_rejected") {
        router.refresh();
      }
    },
    [router],
  );

  useNotificationStream("live-unlock", onInsert);
  return null;
}

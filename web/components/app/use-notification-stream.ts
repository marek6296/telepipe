"use client";

import { useEffect, useMemo } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/client";
import type { NotificationRow } from "@/lib/notifications-ui";

/**
 * Odber nových notifikácií cez Supabase Realtime.
 *
 * Realtime rešpektuje RLS, takže každý dostane len svoje riadky — ale IBA ak je
 * spojenie autentifikované. Preto sa najprv počká na session a explicitne sa
 * zavolá `realtime.setAuth`: kanál otvorený skôr, než sa session načíta
 * z cookies, by ticho nedostal nič. Toto je najčastejšia pasca pri prvom
 * nasadení Realtime a stojí za tie tri riadky navyše.
 *
 * Počúvame len INSERT — zmena `read_at` je naša vlastná a vieme o nej.
 */
export function useNotificationStream(
  channelName: string,
  onInsert: (row: NotificationRow) => void,
) {
  const supabase = useMemo(() => createClient(), []);

  useEffect(() => {
    let channel: RealtimeChannel | null = null;
    let cancelled = false;

    (async () => {
      const { data } = await supabase.auth.getSession();
      if (cancelled || !data.session) return;
      supabase.realtime.setAuth(data.session.access_token);

      channel = supabase
        .channel(channelName)
        .on(
          "postgres_changes",
          { event: "INSERT", schema: "public", table: "notifications" },
          (payload) => onInsert(payload.new as NotificationRow),
        )
        .subscribe();
    })();

    return () => {
      cancelled = true;
      if (channel) supabase.removeChannel(channel);
    };
    // `onInsert` sa zámerne nesleduje — volajúci ho drží v `useCallback`,
    // inak by sa kanál otváral znova pri každom rendri.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supabase, channelName]);

  return supabase;
}

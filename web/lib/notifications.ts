import { createClient } from "@/lib/supabase/server";

/**
 * Notifikácie — SERVEROVÉ čítanie. Zapisuje ich výhradne DB (`notify_account()`
 * a triggery z migrácie 20260819130000), appka ich len číta a označuje
 * prečítané. RLS pustí iba vlastné riadky, takže filter na `account_id` nikde
 * netreba.
 *
 * Typy a zoznam stĺpcov sú v `lib/notifications-ui.ts`, aby ich mohol
 * importovať aj client komponent.
 */

export type { NotificationKind, NotificationRow } from "@/lib/notifications-ui";
export { NOTIFICATION_COLUMNS } from "@/lib/notifications-ui";

/**
 * Počet neprečítaných pre bodku na zvončeku. `head: true` = server vráti len
 * Content-Range, nie riadky; hlavička to volá pri každom rendri.
 */
export async function unreadNotificationCount(): Promise<number> {
  const supabase = await createClient();
  const { count } = await supabase
    .from("notifications")
    .select("id", { count: "exact", head: true })
    .is("read_at", null);
  return count ?? 0;
}

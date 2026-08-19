import { ChatDock } from "@/components/chat/chat-dock";
import { isAdminRole } from "@/lib/admin-ui";
import { listChatRooms } from "@/lib/chat";
import { getAccount } from "@/lib/models";
import { createClient, getUser } from "@/lib/supabase/server";

/**
 * Serverový obal docku — dotiahne, čo klient nemá ako zistiť sám, a vykreslí
 * bublinu. Mountuje sa v `/app` aj na `/locked`.
 *
 * Neprihlásenému nevykreslí nič: chat je vec účtu.
 */
export async function ChatDockMount() {
  const [user, account] = await Promise.all([getUser(), getAccount()]);
  if (!user) return null;

  const supabase = await createClient();
  const [rooms, unread] = await Promise.all([
    listChatRooms(),
    supabase.rpc("chat_unread_total").then(({ data }) => Number(data ?? 0)),
  ]);

  return (
    <ChatDock
      rooms={rooms}
      meId={user.id}
      isAdmin={isAdminRole(account?.role)}
      initialUnread={unread}
    />
  );
}

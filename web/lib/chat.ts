import { createClient } from "@/lib/supabase/server";
import type { ChatRoom } from "@/lib/chat-ui";

/**
 * Chat — SERVEROVÉ čítanie. RLS (`chat_room_visible`) rozhoduje, čo sa vráti,
 * takže filtre na viditeľnosť sa tu neopakujú: druhá kópia pravidla by sa raz
 * rozišla s prvou.
 */

export type { ChatRoom, ChatMessage, RoomKind } from "@/lib/chat-ui";

/**
 * Miestnosti, ktoré tento človek vidí. Zamknutý dostane iba `community`,
 * odomknutý aj `community_plus`. DM sa zakladá až na kliknutie
 * (`my_dm_room()`), aby nevznikala prázdna konverzácia každému, kto sa
 * zaregistruje a odíde.
 */
export async function listChatRooms(): Promise<ChatRoom[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("chat_rooms")
    .select("id, kind, owner_account_id")
    .order("kind", { ascending: true });

  if (error) return [];
  return (data ?? []) as ChatRoom[];
}

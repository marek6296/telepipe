"use server";

import { requireUser } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import { CHAT_MESSAGE_COLUMNS, type ChatMessage } from "@/lib/chat-ui";
import { notifyAdminDirectMessage } from "@/lib/telegram-admin";

export type SendResult = { message?: ChatMessage; error?: string };

/**
 * Odoslanie správy.
 *
 * Ide cez server action, nie priamym insertom z prehliadača, kvôli jednej veci:
 * DM Marekovi musí zároveň cinknúť do Telegramu, a to prehliadač spraviť nemá
 * ako (token by musel byť verejný). Jedna cesta = jedno miesto, kde sa to
 * pamätá.
 *
 * Autorizáciu robí RLS (`chat_can_post`) — umlčaný ani nepozvaný neprejde ani
 * odtiaľto.
 */
export async function sendChatMessageAction(
  roomId: string,
  body: string,
  imagePath = "",
): Promise<SendResult> {
  const user = await requireUser();
  const text = body.trim().slice(0, 4000);
  if (!text && !imagePath) return { error: "Write something first." };

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("chat_messages")
    .insert({ room_id: roomId, sender_id: user.id, body: text, image_path: imagePath })
    .select(CHAT_MESSAGE_COLUMNS)
    .single();

  if (error || !data) {
    // RLS odmietnutie vyzerá ako obyčajná chyba — preložíme ju na vetu, ktorá
    // človeku niečo povie.
    if (error?.message.includes("row-level security")) {
      return { error: "You can't post in this channel." };
    }
    return { error: "Could not send. Try again." };
  }

  const message = data as ChatMessage;

  // Ping do Telegramu iba pri DM a iba keď píše KLIENT — Marekova vlastná
  // odpoveď nemá dôvod cinkať jemu samému.
  const { data: room } = await supabase
    .from("chat_rooms")
    .select("kind, owner_account_id")
    .eq("id", roomId)
    .maybeSingle();

  if (room?.kind === "admin_dm" && room.owner_account_id === user.id) {
    await notifyAdminDirectMessage({
      email: user.email ?? "",
      body: text || "(photo)",
      hasPhoto: Boolean(imagePath),
    });
  }

  return { message };
}

/** Označí miestnosť prečítanú po `last_read_at`. */
export async function markRoomReadAction(roomId: string): Promise<void> {
  const user = await requireUser();
  const supabase = await createClient();
  await supabase
    .from("chat_reads")
    .upsert(
      { room_id: roomId, account_id: user.id, last_read_at: new Date().toISOString() },
      { onConflict: "room_id,account_id" },
    );
}

/** Moja DM na admina — založí sa až tu, nie pri registrácii. */
export async function openDirectMessageAction(): Promise<{ roomId?: string; error?: string }> {
  await requireUser();
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("my_dm_room");
  if (error || !data) return { error: "Could not open the conversation." };
  return { roomId: String(data) };
}

/** Admin: soft delete cudzej správy. */
export async function deleteChatMessageAction(id: string): Promise<{ error?: string }> {
  await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.rpc("admin_delete_chat_message", { p_id: id });
  if (error) return { error: "Could not remove that message." };
  return {};
}

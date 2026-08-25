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

/**
 * Označí miestnosť prečítanú po `last_read_at`.
 *
 * PREČO RPC A NIE `upsert`. PostgREST z upsertu spraví
 * `ON CONFLICT DO UPDATE SET room_id=…, account_id=…, last_read_at=…` a
 * Postgres kontroluje práva na tie stĺpce STATICKY — teda aj vtedy, keď ku
 * konfliktu nedôjde. `authenticated` má UPDATE len na `last_read_at`, takže
 * každý zápis padal na „permission denied" a chyba sa nekontrolovala:
 * `chat_reads` bola prázdna a odznak neprečítaných správ nezmizol nikomu
 * nikdy. Účet si funkcia berie z tokenu, takže netreba grant, ktorý by
 * dovolil prepísať cudziu značku.
 *
 * Vracia `false`, keď sa zápis nepodaril. Volajúci na to nemusí reagovať, ale
 * nesmie to ostať neviditeľné — presne na tom sa táto chyba držala mesiace.
 */
export async function markRoomReadAction(roomId: string): Promise<boolean> {
  await requireUser();
  const supabase = await createClient();
  const { error } = await supabase.rpc("chat_mark_read", { p_room: roomId });
  if (error) {
    console.error("chat_mark_read failed", { roomId, message: error.message });
    return false;
  }
  return true;
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

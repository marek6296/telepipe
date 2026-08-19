import { NextResponse, type NextRequest } from "next/server";

import { telegramAdminChatId, telegramAdminWebhookSecret } from "@/lib/env";
import { createServiceClient } from "@/lib/supabase/server";
import { answerCallback, editMessageText } from "@/lib/telegram-admin";

export const dynamic = "force-dynamic";

/**
 * Webhook Marekovho súkromného admin bota — obsluhuje tlačidlá pod správou
 * o novej žiadosti o prístup.
 *
 * TRI NEZÁVISLÉ KONTROLY, každá by v podstate stačila sama:
 *   1. secret token v hlavičke (nastavený pri `setWebhook`)
 *   2. `chat.id` sedí s `TELEGRAM_ADMIN_CHAT_ID` — kto bota nájde a napíše mu,
 *      neschváli nič
 *   3. `decide_access_request` je service_role-only; `authenticated` ju nemá
 *
 * Vraciame 200 aj pri odmietnutí: Telegram na non-200 doručovanie opakuje
 * a nezmyselný update by sa nám vracal donekonečna.
 */
export async function POST(request: NextRequest) {
  const secret = telegramAdminWebhookSecret();
  const adminChatId = telegramAdminChatId();

  if (!secret || !adminChatId) return NextResponse.json({ ok: true });
  if (request.headers.get("x-telegram-bot-api-secret-token") !== secret) {
    return NextResponse.json({ ok: true });
  }

  let update: {
    callback_query?: {
      id: string;
      data?: string;
      message?: { message_id: number; chat?: { id: number } };
    };
  };
  try {
    update = await request.json();
  } catch {
    return NextResponse.json({ ok: true });
  }

  const query = update.callback_query;
  if (!query?.data || !query.message?.chat) return NextResponse.json({ ok: true });
  if (String(query.message.chat.id) !== adminChatId) {
    return NextResponse.json({ ok: true });
  }

  const match = /^acc:(ok|no):([0-9a-f-]{36})$/.exec(query.data);
  if (!match) return NextResponse.json({ ok: true });

  const approve = match[1] === "ok";
  const requestId = match[2];

  const supabase = createServiceClient();

  // Herca do auditu berieme z DB: že klikol Marek, vieme z chat id, ale zapísať
  // treba jeho účet — a superadmin je práve jeden (seedovaný v migrácii 009).
  const { data: admin } = await supabase
    .from("accounts")
    .select("id")
    .eq("role", "superadmin")
    .order("created_at", { ascending: true })
    .limit(1)
    .maybeSingle();

  if (!admin) {
    await answerCallback(query.id, "No superadmin account found.");
    return NextResponse.json({ ok: true });
  }

  const { data: status, error } = await supabase.rpc("decide_access_request", {
    p_id: requestId,
    p_approve: approve,
    p_note: approve ? "" : "Rejected from Telegram",
    p_actor: admin.id,
  });

  if (error) {
    console.error("decide_access_request failed:", error.message);
    await answerCallback(query.id, "Failed — try the web panel.");
    return NextResponse.json({ ok: true });
  }

  const decided = String(status);
  await answerCallback(query.id, decided === "approved" ? "Approved" : "Rejected");
  await editMessageText({
    chatId: query.message.chat.id,
    messageId: query.message.message_id,
    text:
      decided === "approved"
        ? "<b>Access request — approved ✅</b>"
        : "<b>Access request — rejected ✖️</b>",
  });

  return NextResponse.json({ ok: true });
}

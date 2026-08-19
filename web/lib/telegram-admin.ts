import "server-only";

import {
  telegramAdminBotToken,
  telegramAdminChatId,
  telegramAdminConfigured,
} from "@/lib/env";

/**
 * Marekov SÚKROMNÝ admin bot (@TelePipe_help_bot).
 *
 * Nemá nič spoločné s control botmi modeliek vo workeri — je to samostatný bot
 * a samostatný kanál. Preto tu žiadny import zo sveta workera nie je a byť
 * nesmie.
 *
 * Odosielanie je ZÁMERNE „best effort": Telegram je doručovacia cesta, nie
 * stav. Keď spadne alebo chýba konfigurácia, žiadosť stále stojí v admin
 * paneli — a to je jediné miesto, kde sa nesmie stratiť.
 */

const API = "https://api.telegram.org";

function config(): { token: string; chatId: string } | null {
  if (!telegramAdminConfigured()) return null;
  return { token: telegramAdminBotToken(), chatId: telegramAdminChatId() };
}

/** Escape pre `parse_mode: HTML` — e-mail ani text od žiadateľa nesmie vedieť
 *  rozbiť správu (ani do nej prepašovať odkaz). */
function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function call(method: string, body: unknown): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(`${API}/bot${cfg.token}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) {
      console.error(`telegram-admin ${method} failed:`, response.status);
    }
    return response.ok;
  } catch (error) {
    console.error(`telegram-admin ${method} threw:`, error);
    return false;
  }
}

export async function notifyAccessRequest(input: {
  requestId: string;
  email: string;
  message: string;
}): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;

  const lines = ["<b>New access request</b>", "", escapeHtml(input.email)];
  if (input.message) lines.push("", escapeHtml(input.message));

  return call("sendMessage", {
    chat_id: cfg.chatId,
    parse_mode: "HTML",
    text: lines.join("\n"),
    reply_markup: {
      inline_keyboard: [
        [
          // `acc:ok:<uuid>` = 43 bajtov; limit callback_data je 64.
          { text: "✅ Approve", callback_data: `acc:ok:${input.requestId}` },
          { text: "✖️ Reject", callback_data: `acc:no:${input.requestId}` },
        ],
      ],
    },
  });
}

export async function answerCallback(id: string, text: string): Promise<boolean> {
  return call("answerCallbackQuery", { callback_query_id: id, text });
}

export async function editMessageText(input: {
  chatId: number | string;
  messageId: number;
  text: string;
}): Promise<boolean> {
  return call("editMessageText", {
    chat_id: input.chatId,
    message_id: input.messageId,
    parse_mode: "HTML",
    text: input.text,
  });
}

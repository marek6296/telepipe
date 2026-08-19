"use server";

import { isUnlocked } from "@/lib/access";
import { getAccount, requireUser } from "@/lib/models";
import { STARS_MAX_USD, STARS_MIN_USD } from "@/lib/stars";
import { createInvoiceLink, sendInvoiceToChat } from "@/lib/telegram-shop";
import { telegramShopConfigured } from "@/lib/env";

export type StarInvoiceResult = {
  /** Odkaz na platobné okno v Telegrame. */
  url?: string;
  /** True, ak sme faktúru zároveň poslali rovno do jeho chatu. */
  sentToChat?: boolean;
  error?: string;
};

/**
 * Vyrobí faktúru na Pipe Coiny v Telegram Stars.
 *
 * Suma sa NEBERIE z klienta naslepo — kontroluje sa rozsah, a počet Stars aj
 * coinov dopočíta server. Keby si klient poslal vlastné číslo Stars, kúpil by
 * si coiny za korunu.
 */
export async function createStarInvoiceAction(usd: number): Promise<StarInvoiceResult> {
  await requireUser();
  const account = await getAccount();

  if (!isUnlocked(account)) {
    return { error: "Your account is not approved yet." };
  }
  if (!telegramShopConfigured()) {
    return { error: "Telegram payments are not available right now." };
  }

  const amount = Math.round(Number(usd));
  if (!Number.isFinite(amount) || amount < STARS_MIN_USD || amount > STARS_MAX_USD) {
    return { error: `Choose an amount between $${STARS_MIN_USD} and $${STARS_MAX_USD}.` };
  }

  const url = await createInvoiceLink(account!.id, amount);
  if (!url) return { error: "Could not start the payment. Try again." };

  // Kto už raz platil, tomu faktúru pošleme aj priamo do chatu — vtedy mu
  // platba naozaj „príde do Telegramu" a nemusí nikam klikať. Odkaz vraciame
  // aj tak, lebo na desktope je klik rýchlejší než hľadanie chatu.
  let sentToChat = false;
  const chatId = (account as { telegram_user_id?: number | null }).telegram_user_id;
  if (chatId) {
    sentToChat = await sendInvoiceToChat(Number(chatId), account!.id, amount);
  }

  return { url, sentToChat };
}

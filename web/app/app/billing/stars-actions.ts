"use server";

import { isUnlocked } from "@/lib/access";
import { getAccount, requireUser } from "@/lib/models";
import { starPack } from "@/lib/stars";
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
 * Z klienta príde IBA počet hviezd a ten musí sedieť na existujúci balík —
 * cenu aj počet coinov si server vyberie z `STAR_PACKS`. Keby sa dalo poslať
 * ľubovoľné číslo, klient by si vypýtal faktúru na jednu hviezdu a dostal
 * coiny za celý balík.
 */
export async function createStarInvoiceAction(stars: number): Promise<StarInvoiceResult> {
  await requireUser();
  const account = await getAccount();

  if (!isUnlocked(account)) {
    return { error: "Your account is not approved yet." };
  }
  if (!telegramShopConfigured()) {
    return { error: "Telegram payments are not available right now." };
  }

  const pack = starPack(Math.round(Number(stars)));
  if (!pack) return { error: "Pick one of the packs." };

  const url = await createInvoiceLink(account!.id, pack);
  if (!url) return { error: "Could not start the payment. Try again." };

  // Kto už raz platil, tomu faktúru pošleme aj priamo do chatu — vtedy mu
  // platba naozaj „príde do Telegramu" a nemusí nikam klikať. Odkaz vraciame
  // aj tak, lebo na desktope je klik rýchlejší než hľadanie chatu.
  let sentToChat = false;
  const chatId = (account as { telegram_user_id?: number | null }).telegram_user_id;
  if (chatId) {
    sentToChat = await sendInvoiceToChat(Number(chatId), account!.id, pack);
  }

  return { url, sentToChat };
}

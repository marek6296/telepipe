import "server-only";

import { telegramShopBotToken, telegramShopConfigured } from "@/lib/env";
import { starsCoinsForUsd, starsForUsd } from "@/lib/stars";

/**
 * Obchodný bot — predaj Pipe Coinov za Telegram Stars.
 *
 * Digitálny tovar sa v Telegrame smie predávať výhradne v Stars
 * (`currency: "XTR"`) a `provider_token` sa nechá PRÁZDNY — žiadna platobná
 * brána sa nepoužíva.
 *
 * Kľúčové rozhodnutie: používame `createInvoiceLink`, nie konverzáciu s botom.
 * Klient tak nemusí bota nikdy spustiť ani nič napísať — klikne v `/app/billing`
 * a otvorí sa mu rovno platobné okno. Kto už raz zaplatil, tomu vieme ďalšiu
 * faktúru poslať priamo do chatu (`sendInvoice`).
 */

const API = "https://api.telegram.org";

/** `payload` má 1–128 bajtov a používateľ ho nikdy nevidí. Nesie si, komu sa
 *  má pripísať — vďaka tomu netreba žiadne párovacie tokeny.
 *
 *  Verzia na začiatku je tam schválne: keby sa tvar raz zmenil, staré faktúry
 *  vystavené pred zmenou musia ostať zaplatiteľné. */
export function buildPayload(accountId: string, usd: number): string {
  return `v1:${accountId}:${usd}`;
}

export type ParsedPayload = { accountId: string; usd: number } | null;

export function parsePayload(payload: string): ParsedPayload {
  const m = /^v1:([0-9a-f-]{36}):(\d+(?:\.\d+)?)$/.exec(payload ?? "");
  if (!m) return null;
  const usd = Number(m[2]);
  if (!Number.isFinite(usd) || usd <= 0) return null;
  return { accountId: m[1], usd };
}

async function call<T>(method: string, body: unknown): Promise<T | null> {
  if (!telegramShopConfigured()) return null;
  try {
    const response = await fetch(`${API}/bot${telegramShopBotToken()}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data = (await response.json()) as { ok: boolean; result?: T; description?: string };
    if (!data.ok) {
      console.error(`telegram-shop ${method} failed:`, data.description);
      return null;
    }
    return data.result ?? null;
  } catch (error) {
    console.error(`telegram-shop ${method} threw:`, error);
    return null;
  }
}

function invoiceBody(accountId: string, usd: number) {
  const stars = starsForUsd(usd);
  const coins = starsCoinsForUsd(usd);
  return {
    title: `${coins.toLocaleString("en-US")} Pipe Coins`,
    description:
      `Tops up your TelePipe balance by $${usd}. Coins are added the moment ` +
      `the payment goes through.`,
    payload: buildPayload(accountId, usd),
    // Prázdny provider_token = platba v Stars. Pri digitálnom tovare je to
    // jediná povolená možnosť.
    provider_token: "",
    currency: "XTR",
    // Pre Stars musí `prices` obsahovať PRESNE jednu položku.
    prices: [{ label: `${coins.toLocaleString("en-US")} Pipe Coins`, amount: stars }],
  };
}

/** Odkaz na faktúru. Klient naň klikne a otvorí sa mu platobné okno — bota
 *  nemusí nikdy spustiť. */
export async function createInvoiceLink(
  accountId: string,
  usd: number,
): Promise<string | null> {
  return call<string>("createInvoiceLink", invoiceBody(accountId, usd));
}

/** Faktúra rovno do chatu. Použiteľné až keď poznáme `telegram_user_id`, čiže
 *  po prvej platbe — vtedy klientovi platba naozaj „príde do Telegramu". */
export async function sendInvoiceToChat(
  chatId: number,
  accountId: string,
  usd: number,
): Promise<boolean> {
  const result = await call<unknown>("sendInvoice", {
    chat_id: chatId,
    ...invoiceBody(accountId, usd),
  });
  return result !== null;
}

/** Bez odpovede do 10 s Telegram platbu zruší, takže sa volá vždy a hneď. */
export async function answerPreCheckout(
  queryId: string,
  ok: boolean,
  errorMessage?: string,
): Promise<void> {
  await call("answerPreCheckoutQuery", {
    pre_checkout_query_id: queryId,
    ok,
    ...(ok ? {} : { error_message: errorMessage ?? "Something went wrong. Try again." }),
  });
}

export async function sendShopMessage(chatId: number, text: string): Promise<void> {
  await call("sendMessage", {
    chat_id: chatId,
    parse_mode: "HTML",
    text,
    link_preview_options: { is_disabled: true },
  });
}

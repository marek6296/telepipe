import "server-only";

import { telegramShopBotToken, telegramShopConfigured } from "@/lib/env";
import { USD_PER_STAR } from "@/lib/stars";

/**
 * Zostatok Stars na našom bote a posledné transakcie.
 *
 * Existuje preto, aby sa Marek nemusel spoliehať na to, že peniaze „niekde sú".
 * Stars sedia na bote, ktorý vlastní jeho Telegram účet, a toto ich ukáže
 * priamo v admin paneli — vrátane toho, čo z nich vyjde po prepočte.
 *
 * Ide priamo na Telegram Bot API, nie do našej DB: našou pravdou je, koľko
 * coinov sme klientovi pripísali, Telegramovou to, koľko Stars nám naozaj leží.
 * Keď sa tie dve čísla rozídu, chceme to vidieť.
 */

const API = "https://api.telegram.org";

export type StarsBalance = {
  stars: number;
  /** Hrubý prepočet na doláre. Skutočná výplata je nižšia — Fragment si berie
   *  ~5 % a Stars sa dajú vybrať až 21 dní po pripísaní. */
  approxUsd: number;
  available: boolean;
};

export type StarTransaction = {
  id: string;
  stars: number;
  date: string;
  /** `incoming` = klient nám zaplatil, `outgoing` = refund alebo výber. */
  direction: "incoming" | "outgoing";
  who: string;
};

async function call<T>(method: string): Promise<T | null> {
  if (!telegramShopConfigured()) return null;
  try {
    const response = await fetch(`${API}/bot${telegramShopBotToken()}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      cache: "no-store",
    });
    const data = (await response.json()) as { ok: boolean; result?: T; description?: string };
    if (!data.ok) {
      console.error(`stars-admin ${method}:`, data.description);
      return null;
    }
    return data.result ?? null;
  } catch (error) {
    console.error(`stars-admin ${method} threw:`, error);
    return null;
  }
}

export async function starsBalance(): Promise<StarsBalance> {
  const result = await call<{ amount: number }>("getMyStarBalance");
  const stars = Number(result?.amount ?? 0);
  return {
    stars,
    approxUsd: stars * USD_PER_STAR,
    available: result !== null,
  };
}

type RawTx = {
  id: string;
  amount: number;
  date: number;
  source?: { user?: { username?: string; first_name?: string } };
  receiver?: { user?: { username?: string; first_name?: string } };
};

export async function starTransactions(): Promise<StarTransaction[]> {
  const result = await call<{ transactions?: RawTx[] }>("getStarTransactions");
  const rows = result?.transactions ?? [];

  return rows.slice(0, 25).map((tx) => {
    // `source` vyplnené = peniaze prišli k nám; `receiver` = odišli od nás.
    const incoming = Boolean(tx.source);
    const party = (incoming ? tx.source : tx.receiver)?.user;
    return {
      id: tx.id,
      stars: tx.amount,
      date: new Date(tx.date * 1000).toISOString(),
      direction: incoming ? "incoming" : "outgoing",
      who: party?.username ? `@${party.username}` : (party?.first_name ?? "—"),
    };
  });
}

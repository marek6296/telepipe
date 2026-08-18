"use server";

import { COIN_PACKS, type CoinPack } from "@/lib/coins";

/**
 * Nákup balíka Pipe Coinov — ZATIAĽ IBA ŠEV.
 *
 * Platby ešte nebežia. Marek na ne chystá **Plisio** (krypto brána), takže táto
 * akcia je zámerne jediné miesto, kde sa to bude zapájať: stránka už dnes volá
 * `startTopUp(packId)` a čaká `TopUpResult`, takže keď brána príde, mení sa telo
 * funkcie a nič v UI.
 *
 * TODO(plisio): tu vytvoriť invoice cez Plisio API a vrátiť
 * `{ status: "redirect", url: invoice.invoice_url }`. Pripísanie coinov NESMIE
 * robiť táto akcia — kredit sa smie zvýšiť až z overeného Plisio callbacku
 * (server-to-server, s kontrolou podpisu), inak si zostatok navýši ktokoľvek,
 * kto vie zavolať server action. Kredit sa pripisuje v USD
 * (`pack.coins / COINS_PER_USD`) cez `admin_add_credit` — jednotka v DB ostáva
 * dolár, viď `lib/coins.ts`.
 */

export type TopUpResult =
  | { status: "unavailable"; contactEmail: string; subject: string }
  | { status: "redirect"; url: string };

/** Kam sa klient obráti, kým brána nebeží. Nesmie byť `export` — súbor je
 *  `"use server"` a ten smie exportovať výhradne async funkcie (typy sa mažú
 *  pri kompilácii, takže `export type` je v poriadku). */
const TOP_UP_EMAIL = "support@telepipe.app";

export async function startTopUp(packId: string): Promise<TopUpResult> {
  const pack: CoinPack | undefined = COIN_PACKS.find((item) => item.id === packId);

  // Neznáme id nesmie skončiť na „kontaktujte nás kvôli undefined" — radšej
  // všeobecná adresa než rozbitý predmet mailu.
  const subject = pack
    ? `Telepipe top-up — ${pack.name} ($${pack.priceUsd})`
    : "Telepipe top-up";

  return { status: "unavailable", contactEmail: TOP_UP_EMAIL, subject };
}

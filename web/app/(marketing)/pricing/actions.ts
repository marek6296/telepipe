"use server";

import { COIN_PACKS, type CoinPack } from "@/lib/coins";
import { plisioEnabled } from "@/lib/plisio";

/**
 * Nákup balíka Pipe Coinov z verejného cenníka.
 *
 * Skutočný checkout žije v appke na `/app/billing` (Plisio white-label:
 * adresa + presná suma + QR priamo u nás). Táto akcia len presmeruje na
 * checkout s predvybraným balíkom — neprihláseného middleware pošle na
 * `/login?next=…`, takže po prihlásení pristane rovno v checkoute.
 *
 * Pripísanie coinov NIKDY nerobí web akcia — kredit smie zvýšiť výhradne
 * `settle_crypto_payment` po overení stavu u Plisia (webhook/poll/cron).
 */

export type TopUpResult =
  | { status: "unavailable"; contactEmail: string; subject: string }
  | { status: "redirect"; url: string };

/** Fallback, kým je brána vypnutá (prázdny PLISIO_SECRET_KEY). */
const TOP_UP_EMAIL = "support@telepipe.app";

export async function startTopUp(packId: string): Promise<TopUpResult> {
  const pack: CoinPack | undefined = COIN_PACKS.find((item) => item.id === packId);

  if (pack && plisioEnabled()) {
    return { status: "redirect", url: `/app/billing?pack=${encodeURIComponent(pack.id)}` };
  }

  // Neznáme id nesmie skončiť na „kontaktujte nás kvôli undefined" — radšej
  // všeobecná adresa než rozbitý predmet mailu.
  const subject = pack
    ? `Telepipe top-up — ${pack.name} ($${pack.priceUsd})`
    : "Telepipe top-up";

  return { status: "unavailable", contactEmail: TOP_UP_EMAIL, subject };
}

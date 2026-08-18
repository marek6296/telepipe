import "server-only";

/**
 * OnRamp Pay (onramp-pay.com) — platba kartou, ktorá skončí ako USDC (Polygon)
 * na našej adrese. SERVER ONLY.
 *
 * Služba nemá registráciu ani API kľúč: `wallet.php` dostane našu výplatnú
 * adresu + callback URL a vráti zašifrovaný `address_in` pre checkout a
 * `ipn_token` na kontrolu stavu. Z toho plynú dve bezpečnostné pravidlá:
 *
 *   1. Callback NIE JE podpísaný. Jediné, čo ho viaže k platbe, je
 *      neuhádnuteľné `payment_id` v URL — a pripísať sa smie až po kladnej
 *      odpovedi `payment-status.php?ipn_token=…`, teda po overení priamo
 *      u služby. Parametre callbacku (value_coin…) sa na pripísanie NIKDY
 *      nepoužívajú.
 *   2. Výplatná adresa musí byť EVM adresa, ktorá REÁLNE prijíma USDC na
 *      POLYGONE. Custodial peňaženky bez podpory Polygonu (napr. Plisio) by
 *      tie tokeny nikdy nezobrazili a boli by nenávratne preč — preto sa
 *      adresa berie z env a aspoň tvarovo validuje.
 */

const API = "https://api.onramp-pay.com/control";
const CHECKOUT = "https://checkout.onramp-pay.com";
const TIMEOUT_MS = 15_000;

const EVM_ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

/** Výplatná adresa (USDC Polygon). Prázdna alebo zlá = funkcia je vypnutá. */
export function onrampPayoutAddress(): string {
  const raw = (process.env.ONRAMP_PAYOUT_ADDRESS ?? "").trim();
  return EVM_ADDRESS_RE.test(raw) ? raw : "";
}

export function onrampEnabled(): boolean {
  return onrampPayoutAddress() !== "";
}

export interface OnrampWallet {
  /** Zašifrovaný token adresy — ide do checkout URL. */
  addressIn: string;
  /** Skutočná dočasná Polygon adresa, kam klient platí. */
  polygonAddressIn: string;
  /** Token na `payment-status.php` — autoritatívne „zaplatené?". */
  ipnToken: string;
}

/**
 * Založí platbu: dočasná adresa naviazaná na náš callback. Volá sa RAZ pri
 * kliknutí na „Pay by card"; výsledok sa uloží k riadku platby.
 */
export async function createWallet(
  callbackUrl: string,
): Promise<{ ok: true; data: OnrampWallet } | { ok: false; error: string }> {
  const address = onrampPayoutAddress();
  if (!address) return { ok: false, error: "OnRamp payout address is not configured." };

  const url = `${API}/wallet.php?address=${address}&callback=${encodeURIComponent(callbackUrl)}`;
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) {
      return { ok: false, error: `OnRamp answered ${response.status}.` };
    }
    const body = (await response.json()) as Record<string, unknown>;
    const addressIn = String(body.address_in ?? "");
    const polygonAddressIn = String(body.polygon_address_in ?? "");
    const ipnToken = String(body.ipn_token ?? "");
    if (!addressIn || !ipnToken) {
      return { ok: false, error: "OnRamp returned an incomplete wallet." };
    }
    return { ok: true, data: { addressIn, polygonAddressIn, ipnToken } };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "OnRamp unreachable." };
  }
}

/**
 * Multi-provider checkout (`pay.php`) — klient si vyberie Stripe/Coinbase/…,
 * podľa regiónu. Fixná suma v USD; e-mail predvyplní formulár.
 */
export function checkoutUrl(addressIn: string, amountUsd: number, email: string): string {
  const query = new URLSearchParams({
    address: addressIn,
    amount: amountUsd.toFixed(2),
    currency: "USD",
    domain: "checkout.onramp-pay.com",
  });
  if (email) query.set("email", email);
  return `${CHECKOUT}/pay.php?${query.toString()}`;
}

/**
 * Autoritatívny stav platby. `paid` | `unpaid` | null (nedostupné/neznáme).
 * Toto je JEDINÝ podklad na pripísanie coinov — viď hlavičku modulu.
 */
export async function paymentStatus(ipnToken: string): Promise<"paid" | "unpaid" | null> {
  if (!ipnToken) return null;
  const url = `${API}/payment-status.php?ipn_token=${encodeURIComponent(ipnToken)}`;
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) return null;
    const text = await response.text();
    let status = "";
    try {
      const body = JSON.parse(text) as Record<string, unknown>;
      status = String(body.status ?? body.payment_status ?? "").toLowerCase();
    } catch {
      status = text.trim().toLowerCase();
    }
    if (status.includes("paid") && !status.includes("unpaid")) return "paid";
    if (status.includes("unpaid") || status.includes("pending")) return "unpaid";
    return null;
  } catch {
    return null;
  }
}

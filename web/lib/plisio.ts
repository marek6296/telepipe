import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";

import { plisioSecretKey } from "@/lib/env";

/**
 * Plisio — krypto platobná brána pre nákup Pipe Coinov.
 *
 * White-label režim (zapnutý v Plisio → Site settings): `/invoices/new` vracia
 * priamo depozitnú adresu + presnú krypto sumu + QR, takže celý checkout beží
 * u nás v appke a klient nikam neodchádza. Poplatok 1,5 % platí site (my).
 *
 * Zdroj pravdy o zaplatení je VŽDY `GET /operations/{txn_id}` s naším secret
 * kľúčom — telu callbacku sa neverí (podvrhnutý POST tak nanajvýš spustí
 * autoritatívnu kontrolu). `verify_hash` callbacku overujeme len ako prvý
 * filter, aby cudzie POSTy nespúšťali zbytočné volania na Plisio API.
 *
 * Docs: https://plisio.net/documentation
 */

const API = "https://api.plisio.net/api/v1";

/** Ako dlho má klient na odoslanie platby. Plisio povoľuje 15 min – 48 h. */
export const INVOICE_EXPIRE_MIN = 60;

export function plisioEnabled(): boolean {
  return Boolean(plisioSecretKey());
}

/**
 * Mince, ktoré predávame. Musia byť zapnuté aj v Plisio → Site settings →
 * Supported currencies (a mať vytvorenú wallet, inak ich Plisio neponúkne).
 * `cid` je Plisio kód meny, `network` je text pre klienta — posiela sa presne
 * na túto sieť, inak o peniaze príde.
 */
export const PAY_CURRENCIES = [
  { cid: "BTC", label: "Bitcoin", network: "Bitcoin" },
  { cid: "ETH", label: "Ethereum", network: "Ethereum (ERC-20)" },
  { cid: "SOL", label: "Solana", network: "Solana" },
  { cid: "LTC", label: "Litecoin", network: "Litecoin" },
  { cid: "TRX", label: "Tron", network: "Tron (TRC-20)" },
  { cid: "BNB", label: "BNB", network: "BNB Smart Chain (BEP-20)" },
  { cid: "BCH", label: "Bitcoin Cash", network: "Bitcoin Cash" },
] as const;

export type PayCurrencyCid = (typeof PAY_CURRENCIES)[number]["cid"];

export function isPayCurrency(value: string): value is PayCurrencyCid {
  return PAY_CURRENCIES.some((c) => c.cid === value);
}

export interface CreateInvoiceInput {
  priceUsd: number;
  currency: PayCurrencyCid;
  orderNumber: string;
  orderName: string;
  /** E-mail klienta — Plisio naň vie poslať potvrdenie o platbe. */
  email: string;
  callbackUrl: string;
}

export interface CreatedInvoice {
  /** Plisio txn_id — kľúč na status aj párovanie callbackov. */
  paymentId: string;
  /** Depozitná adresa (wallet_hash). */
  payAddress: string;
  /** Presná krypto suma, ktorú musí klient poslať. */
  payAmount: number;
  payCurrency: string;
  status: string;
  /** Plisiov hotový QR (data URI) — obsahuje adresu aj sumu. */
  qrCode: string;
  /**
   * Hostovaná platobná stránka (Alternative Payment Link). Pri white-label
   * shope chodí len keď je v Plisio Site settings zapnutý „Activate
   * Alternative Payment Link" — ponúkame ju ako záložnú cestu.
   */
  invoiceUrl: string;
  /** Kedy faktúra vyprší (ISO). Null, keď Plisio čas nedal. */
  expireAt: string | null;
}

/** Plisio `expire_utc` chodí ako unix timestamp — niekedy v sekundách, niekedy v ms. */
function parseExpireUtc(value: unknown): string | null {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return null;
  const ms = n > 1e12 ? n : n * 1000;
  const d = new Date(ms);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export async function createInvoice(
  input: CreateInvoiceInput,
): Promise<{ ok: true; data: CreatedInvoice } | { ok: false; error: string }> {
  try {
    const params = new URLSearchParams({
      source_currency: "USD",
      source_amount: String(input.priceUsd),
      currency: input.currency,
      // Zamknúť fakturáciu na zvolenú mincu — prepnutie meny by založilo
      // súrodeneckú faktúru a párovanie by sa skomplikovalo.
      allowed_psys_cids: input.currency,
      order_number: input.orderNumber,
      order_name: input.orderName,
      email: input.email,
      expire_min: String(INVOICE_EXPIRE_MIN),
      callback_url: input.callbackUrl,
      api_key: plisioSecretKey(),
      json: "true",
    });
    const res = await fetch(`${API}/invoices/new?${params.toString()}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const j = (await res.json().catch(() => ({}))) as {
      status?: string;
      data?: Record<string, unknown>;
      message?: string;
    };
    if (j.status !== "success" || !j.data) {
      const d = j.data as Record<string, unknown> | undefined;
      return {
        ok: false,
        error: (d?.message as string) || j.message || `Plisio error (${res.status})`,
      };
    }

    const d = j.data;
    const address = String(d.wallet_hash ?? "");
    const amount = Number(d.amount ?? d.pending_amount ?? 0);
    const txnId = String(d.txn_id ?? d.id ?? "");
    // Bez adresy/sumy nemáme čo ukázať — typicky vypnutý white-label alebo
    // minca bez peňaženky. Nič sa nezapisuje.
    if (!address || !txnId || !Number.isFinite(amount) || amount <= 0) {
      return { ok: false, error: "Plisio returned an incomplete invoice. Try another coin." };
    }

    const qr = typeof d.qr_code === "string" ? d.qr_code.trim() : "";
    return {
      ok: true,
      data: {
        paymentId: txnId,
        payAddress: address,
        payAmount: amount,
        payCurrency: String(d.currency ?? d.psys_cid ?? input.currency),
        status: String(d.status ?? "new"),
        // qr_code môže prísť ako holé base64 bez data: prefixu.
        qrCode: qr && !qr.startsWith("data:") ? `data:image/png;base64,${qr}` : qr,
        invoiceUrl: typeof d.invoice_url === "string" ? d.invoice_url.trim() : "",
        expireAt: parseExpireUtc(d.expire_utc),
      },
    };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}

export interface PlisioOperation {
  /** "new" | "pending" | "pending internal" | "completed" | "mismatch" | "expired" | "cancelled" | "error" | … */
  status: string;
  /** Krypto suma, ktorú faktúra pýtala (null = Plisio nepovedalo). */
  expected: number | null;
  /** Krypto suma, ktorá reálne prišla (null = Plisio nepovedalo). */
  received: number | null;
}

/**
 * Autoritatívny stav faktúry — pýta sa naším secret kľúčom. Volá ho webhook
 * (ako re-check), browser poller aj cron reconciler.
 */
export async function getOperation(txnId: string): Promise<PlisioOperation | null> {
  try {
    const res = await fetch(
      `${API}/operations/${encodeURIComponent(txnId)}?api_key=${encodeURIComponent(plisioSecretKey())}`,
      { headers: { Accept: "application/json" }, cache: "no-store" },
    );
    const j = (await res.json().catch(() => ({}))) as {
      status?: string;
      data?: Record<string, unknown>;
    };
    if (j.status !== "success" || !j.data || j.data.status == null) return null;
    const d = j.data;

    // Názvy polí v Plisio odpovediach kolíšu — skúšame známe varianty a pri
    // neistote ostávame na null (neznáma suma sa NIKDY neberie ako zaplatená).
    const num = (...vals: unknown[]): number | null => {
      for (const v of vals) {
        const n = Number(v);
        if (Number.isFinite(n) && n > 0) return n;
      }
      return null;
    };
    const params = (d.params ?? {}) as Record<string, unknown>;
    return {
      status: String(d.status),
      expected: num(d.amount, params.amount, d.pending_sum, d.invoice_total_sum),
      received: num(d.actual_sum, d.received_amount, d.amount_received, d.paid_sum, d.actual_amount),
    };
  } catch {
    return null;
  }
}

/**
 * Overenie `verify_hash` z JSON callbacku (`callback_url` má `?json=true`):
 * HMAC-SHA1 cez kompaktný JSON tela bez `verify_hash`, v pôvodnom poradí
 * kľúčov, kľúčom je secret key. Slúži len ako lacný filter pred re-checkom —
 * pravda o zaplatení sa aj tak číta z `/operations/{id}`.
 */
export function verifyCallbackHash(rawBody: string): boolean {
  try {
    const data = JSON.parse(rawBody) as Record<string, unknown>;
    const given = String(data.verify_hash ?? "");
    if (!given) return false;
    delete data.verify_hash;
    const message = JSON.stringify(data);
    const expected = createHmac("sha1", plisioSecretKey()).update(message).digest("hex");
    const a = Buffer.from(expected, "utf8");
    const b = Buffer.from(given, "utf8");
    return a.length === b.length && timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

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
// Plisio documents permanent deposit addresses on the main API host, while
// invoice and operation endpoints use api.plisio.net.
const DEPOSIT_API = "https://plisio.net/api/v1";

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
  { cid: "USDT_TRX", label: "USDT", network: "Tron (TRC-20)" },
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

export interface PermanentDepositAddress {
  depositUid: string;
  payAddress: string;
  payCurrency: PayCurrencyCid;
}

/**
 * Create the permanent address that Plisio associates with our account UUID.
 * Repeated transfers to this address arrive as `pay_in` operations; there is
 * no invoice, countdown, or amount lock.
 */
export async function createPermanentDepositAddress(input: {
  depositUid: string;
  currency: PayCurrencyCid;
}): Promise<
  { ok: true; data: PermanentDepositAddress } | { ok: false; error: string }
> {
  try {
    const params = new URLSearchParams({
      psys_cid: input.currency,
      uid: input.depositUid,
      api_key: plisioSecretKey(),
    });
    const res = await fetch(`${DEPOSIT_API}/shops/deposit/new?${params.toString()}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const j = (await res.json().catch(() => ({}))) as {
      status?: string;
      data?: Record<string, unknown>;
      message?: string;
    };
    if (j.status !== "success" || !j.data) {
      return {
        ok: false,
        error:
          String(j.data?.message ?? j.message ?? "") ||
          `Plisio deposit error (${res.status})`,
      };
    }

    const address = String(j.data.hash ?? "").trim();
    const uid = String(j.data.uid ?? input.depositUid).trim();
    const currency = String(j.data.psys_cid ?? input.currency).toUpperCase();
    if (!address || uid !== input.depositUid || currency !== input.currency) {
      return { ok: false, error: "Plisio returned an incomplete deposit address." };
    }
    return {
      ok: true,
      data: { depositUid: uid, payAddress: address, payCurrency: input.currency },
    };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
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
  /** Operation metadata used by permanent `pay_in` reconciliation. */
  paymentId: string;
  type: string;
  payCurrency: string;
  payAddress: string;
  depositUid: string;
  sourceUsd: number | null;
  txUrls: string[];
}

const positiveNumber = (...values: unknown[]): number | null => {
  for (const value of values) {
    const n = Number(value);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return null;
};

function stringArray(...values: unknown[]): string[] {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value.map(String).map((item) => item.trim()).filter(Boolean);
    }
    if (typeof value === "string" && value.trim()) {
      const text = value.trim();
      if (text.startsWith("[")) {
        try {
          const parsed = JSON.parse(text) as unknown;
          if (Array.isArray(parsed)) {
            return parsed.map(String).map((item) => item.trim()).filter(Boolean);
          }
        } catch {
          // A single explorer URL is also a valid response.
        }
      }
      return [text];
    }
  }
  return [];
}

/** Normalized completed transfer received on a permanent Plisio address. */
export interface PlisioPayIn {
  paymentId: string;
  status: string;
  currency: string;
  payAddress: string;
  depositUid: string;
  cryptoReceived: number;
  /** Net provider-confirmed value in USD, used for credit and bonus tiers. */
  sourceUsd: number;
  txUrls: string[];
}

/**
 * Normalize either a signed pay-in callback or a pay-in operation returned by
 * `/operations`. Returns null rather than guessing when the USD value is not
 * provable from the provider fields.
 */
export function parsePlisioPayIn(data: Record<string, unknown>): PlisioPayIn | null {
  const params = (data.params ?? {}) as Record<string, unknown>;
  const kind = String(data.ipn_type ?? data.type ?? "").toLowerCase();
  if (kind !== "pay_in") return null;

  const paymentId = String(data.txn_id ?? data.id ?? "").trim();
  const status = String(data.status ?? "").trim().toLowerCase();
  const currency = String(data.psys_cid ?? data.currency ?? "").trim().toUpperCase();
  const payAddress = String(data.wallet_hash ?? "").trim();
  const depositUid = String(data.deposit_uid ?? data.uid ?? params.deposit_uid ?? "").trim();
  const cryptoReceived = positiveNumber(
    data.deposit_sum,
    data.invoice_sum,
    data.actual_sum,
    data.sum,
    data.amount,
  );

  const sourceCurrency = String(
    data.source_currency ?? params.source_currency ?? "USD",
  ).toUpperCase();
  const explicitUsd = positiveNumber(data.source_amount, params.source_amount);
  const sourceRate = positiveNumber(data.source_rate, params.source_rate);
  // Plisio expresses `source_rate` as crypto units per one source-currency
  // unit (its invoice example uses BTC amount = USD × source_rate).
  const sourceUsd =
    sourceCurrency === "USD"
      ? explicitUsd ??
        (cryptoReceived != null && sourceRate != null ? cryptoReceived / sourceRate : null)
      : null;

  if (
    !paymentId ||
    !status ||
    !currency ||
    !payAddress ||
    cryptoReceived == null ||
    sourceUsd == null ||
    !Number.isFinite(sourceUsd) ||
    sourceUsd <= 0
  ) {
    return null;
  }

  return {
    paymentId,
    status,
    currency,
    payAddress,
    depositUid,
    cryptoReceived,
    sourceUsd,
    txUrls: stringArray(data.tx_urls, data.tx_url),
  };
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

    const params = (d.params ?? {}) as Record<string, unknown>;
    const payIn = parsePlisioPayIn(d);
    return {
      status: String(d.status),
      expected: positiveNumber(d.amount, params.amount, d.pending_sum, d.invoice_total_sum),
      received: positiveNumber(
        d.actual_sum,
        d.received_amount,
        d.amount_received,
        d.paid_sum,
        d.actual_amount,
      ),
      paymentId: String(d.id ?? txnId),
      type: String(d.type ?? ""),
      payCurrency: String(d.psys_cid ?? d.currency ?? "").toUpperCase(),
      payAddress: String(d.wallet_hash ?? ""),
      depositUid: payIn?.depositUid ?? String(d.deposit_uid ?? params.deposit_uid ?? ""),
      sourceUsd: payIn?.sourceUsd ?? null,
      txUrls: stringArray(d.tx_urls, d.tx_url),
    };
  } catch {
    return null;
  }
}

/**
 * Autoritatívny stav jednej pay_in operácie — pýta sa naším secret kľúčom.
 * Webhook ním overuje callbacky, ktorých `verify_hash` nesedí: pripísanie tak
 * ostáva okamžité aj pri inom formáte podpisu a podvrhnutý callback nič
 * nezmôže, lebo dáta idú vždy z Plisio API, nie z tela požiadavky.
 */
export async function getPayInOperation(txnId: string): Promise<PlisioPayIn | null> {
  try {
    const res = await fetch(
      `${API}/operations/${encodeURIComponent(txnId)}?api_key=${encodeURIComponent(plisioSecretKey())}`,
      { headers: { Accept: "application/json" }, cache: "no-store" },
    );
    const j = (await res.json().catch(() => ({}))) as {
      status?: string;
      data?: Record<string, unknown>;
    };
    if (j.status !== "success" || !j.data) return null;
    return parsePlisioPayIn(j.data);
  } catch {
    return null;
  }
}

/** Recent permanent-address transfers, used only as a webhook-loss backstop. */
export async function listPayInOperations(
  page = 1,
  limit = 100,
): Promise<PlisioPayIn[]> {
  try {
    const params = new URLSearchParams({
      api_key: plisioSecretKey(),
      type: "pay_in",
      status: "completed",
      page: String(page),
      limit: String(limit),
    });
    const res = await fetch(`${API}/operations?${params.toString()}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const j = (await res.json().catch(() => ({}))) as {
      status?: string;
      data?: { operations?: Record<string, unknown>[] };
    };
    if (j.status !== "success" || !Array.isArray(j.data?.operations)) return [];
    return j.data.operations
      .map((operation) => parsePlisioPayIn(operation))
      .filter((operation): operation is PlisioPayIn => operation != null);
  } catch {
    return [];
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

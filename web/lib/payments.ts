import "server-only";

import {
  getOperation,
  listPayInOperations,
  plisioEnabled,
  type PlisioOperation,
  type PlisioPayIn,
} from "@/lib/plisio";
import { createServiceClient } from "@/lib/supabase/server";

/**
 * Zúčtovanie Plisio platieb. Pripísanie kreditu robí výhradne DB funkcia
 * `settle_crypto_payment` (jedna transakcia, row lock, unique ledger) — tento
 * modul len rozhoduje, ČI je platba zaplatená, a volá ju.
 *
 * K pripísaniu vedú tri nezávislé cesty a všetky končia tu:
 *   (A) Plisio IPN  → POST /api/payments/webhook
 *   (B) browser     → GET  /api/payments/topup?payment_id=… (poll každých 8 s)
 *   (C) Vercel cron → GET  /api/payments/reconcile
 * Webhook sa môže stratiť, prehliadač zavrieť — cron to do 72 h dotiahne.
 */

const T = "crypto_payments";

/** Stavy, ktoré znamenajú plne zaplatené bez ďalšieho skúmania. */
const PAID_STATUSES = new Set(["completed", "finished"]);
/**
 * Stavy, ktoré sa už nezmenia a NEMÁ zmysel ich naháňať. `expired` tu zámerne
 * NIE JE: peniaze poslané tesne po vypršaní na adrese reálne pristanú a
 * `paidEnough` ich podľa súm pripíše — reconciler ich preto sleduje ďalej.
 */
const FINAL_STATUSES = new Set([
  "completed",
  "finished",
  "cancelled",
  "cancelled duplicate",
  "cancelled_duplicate",
  "error",
  "refunded",
]);
/** Tolerancia na zaokrúhľovanie pri porovnaní prijatej vs. fakturovanej sumy. */
const AMOUNT_TOLERANCE = 0.99;

export interface SettleResult {
  found: boolean;
  credited: boolean;
  status: string | null;
  balance?: number;
}

/**
 * Zaplatil klient naozaj dosť?
 *
 * `mismatch` = prišlo iné než fakturované — PREPLATOK je stále zaplatené a
 * musí pripísať. `expired` s plnou sumou = platba prišla po vypršaní, peniaze
 * máme, klient nesmie prísť o coiny. V oboch prípadoch pripisujeme len keď
 * Plisio dalo OBE čísla a prijaté ≥ 99 % fakturovaného — neznáma alebo nižšia
 * suma sa nikdy neberie ako zaplatená (nedoplatky rieši Plisio nastavenie
 * „Underpayment allowed %", ktoré ich samo prepne na completed).
 */
export function paidEnough(status: string, op?: Pick<PlisioOperation, "expected" | "received">): boolean {
  if (PAID_STATUSES.has(status)) return true;
  if (status !== "mismatch" && status !== "expired") return false;
  const expected = op?.expected ?? null;
  const received = op?.received ?? null;
  if (expected == null || received == null) return false;
  return received >= expected * AMOUNT_TOLERANCE;
}

/**
 * Zapíš najnovší stav platby a pri prvom skutočnom zaplatení pripíš Pipe
 * Coiny. Idempotentné a race-safe — atomicitu rieši DB funkcia.
 */
export async function settlePayment(
  paymentId: string,
  status: string,
  op?: Pick<PlisioOperation, "expected" | "received">,
): Promise<SettleResult | null> {
  const admin = createServiceClient();
  const { data, error } = await admin.rpc("settle_crypto_payment", {
    p_payment_id: paymentId,
    p_status: status,
    p_paid: paidEnough(status, op),
  });
  if (error) {
    console.error("settle_crypto_payment failed:", error.message);
    return null;
  }
  return (data ?? null) as SettleResult | null;
}

/**
 * Doptaj sa POSKYTOVATEĽA na aktuálny stav a zúčtuj. Jedno miesto pre všetky
 * cesty (webhook, poll, cron) a pre oboch providerov:
 *
 *   plisio → getOperation (secret key, stavy completed/mismatch/expired…)
 *   onramp → payment-status.php (ipn_token; binárne paid/unpaid, takže sumy
 *            netreba — „paid" znamená, že USDC odišlo na našu adresu)
 */
export async function refreshPayment(paymentId: string): Promise<SettleResult | null> {
  const admin = createServiceClient();
  const { data: row } = await admin
    .from(T)
    .select("provider, provider_token")
    .eq("payment_id", paymentId)
    .maybeSingle();

  if (row?.provider === "onramp") {
    const { paymentStatus } = await import("@/lib/onramp");
    const status = await paymentStatus(String(row.provider_token ?? ""));
    if (status === null) return null;
    return status === "paid"
      ? settlePayment(paymentId, "completed")
      : settlePayment(paymentId, "pending_confirm");
  }

  if (!plisioEnabled()) return null;
  const op = await getOperation(paymentId);
  if (!op) return null;
  return settlePayment(paymentId, op.status, op);
}

/**
 * Backstop reconciler (Vercel cron). Prejde všetky nepripísané platby za
 * posledných 72 hodín a doptá sa Plisia — TOTO je odpoveď na „čo keď klient
 * zaplatí neskôr / webhook sa stratí / zavrie stránku".
 */
export async function reconcileOpenPayments(
  maxAgeHours = 72,
): Promise<{ checked: number; credited: number }> {
  const admin = createServiceClient();
  const since = new Date(Date.now() - maxAgeHours * 3_600_000).toISOString();

  const { data: rows } = await admin
    .from(T)
    .select("payment_id, status, provider")
    .eq("credited", false)
    .gte("created_at", since)
    .limit(100);

  let checked = 0;
  let credited = 0;
  for (const row of rows ?? []) {
    if (FINAL_STATUSES.has(String(row.status))) continue;
    // Vypnutý provider sa preskočí namiesto toho, aby zhodil celý beh —
    // onramp platby sa naháňajú aj keď Plisio kľúč chýba, a naopak.
    if (String(row.provider ?? "plisio") === "plisio" && !plisioEnabled()) continue;
    const out = await refreshPayment(String(row.payment_id));
    if (!out) continue;
    checked += 1;
    if (out.credited) credited += 1;
  }
  return { checked, credited };
}

export interface DepositSettleResult extends SettleResult {
  coins?: number;
  sourceUsd?: number;
}

/**
 * Settle a completed transfer received at one of our permanent addresses.
 * Address ownership is resolved server-side and checked once more inside the
 * SECURITY DEFINER database function. `paymentId` is unique, so webhook and
 * cron may race safely without ever double-crediting.
 */
export async function settlePermanentDeposit(
  deposit: PlisioPayIn,
): Promise<DepositSettleResult | null> {
  if (!PAID_STATUSES.has(deposit.status)) return null;

  const admin = createServiceClient();
  const query = admin
    .from("crypto_deposit_addresses")
    .select("id, account_id, deposit_uid, pay_currency, pay_address")
    .eq("pay_currency", deposit.currency)
    .eq("pay_address", deposit.payAddress);
  const { data: byAddress, error: addressError } = await query.maybeSingle();
  if (addressError) {
    console.error("permanent deposit address lookup failed:", addressError.message);
    return null;
  }

  const address = byAddress;
  if (!address?.account_id) return null;
  if (deposit.depositUid && address.deposit_uid !== deposit.depositUid) return null;
  if (address.pay_currency !== deposit.currency) return null;
  if (address.pay_address !== deposit.payAddress) return null;

  const { data, error } = await admin.rpc("settle_crypto_deposit", {
    p_payment_id: deposit.paymentId,
    p_account_id: address.account_id,
    p_deposit_uid: address.deposit_uid,
    p_pay_currency: address.pay_currency,
    p_pay_address: address.pay_address,
    p_crypto_received: deposit.cryptoReceived,
    p_source_usd: deposit.sourceUsd,
    p_status: deposit.status,
    p_tx_urls: deposit.txUrls,
  });
  if (error) {
    console.error("settle_crypto_deposit failed:", error.message);
    return null;
  }
  return (data ?? null) as DepositSettleResult | null;
}

/**
 * Permanent addresses have no open invoice row to poll. Scan recent completed
 * pay-ins as a five-minute backstop when an IPN is delayed or lost. Existing
 * transaction IDs are filtered before calling the settlement RPC.
 */
export async function reconcilePermanentDeposits(): Promise<{
  checked: number;
  credited: number;
}> {
  if (!plisioEnabled()) return { checked: 0, credited: 0 };

  const admin = createServiceClient();
  let checked = 0;
  let credited = 0;

  // Three pages cover the 300 most recent confirmed pay-ins. Lists are
  // newest-first; running every five minutes keeps this comfortably ahead.
  for (let page = 1; page <= 3; page += 1) {
    const operations = await listPayInOperations(page, 100);
    if (operations.length === 0) break;

    const ids = operations.map((operation) => operation.paymentId);
    const { data: known } = await admin
      .from("crypto_deposit_events")
      .select("payment_id")
      .in("payment_id", ids);
    const knownIds = new Set((known ?? []).map((row) => String(row.payment_id)));

    for (const operation of operations) {
      if (knownIds.has(operation.paymentId)) continue;
      checked += 1;
      const out = await settlePermanentDeposit(operation);
      if (out?.credited) credited += 1;
    }

    if (operations.length < 100) break;
  }

  return { checked, credited };
}

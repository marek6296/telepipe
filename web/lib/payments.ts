import "server-only";

import { getOperation, plisioEnabled, type PlisioOperation } from "@/lib/plisio";
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

/** Doptaj sa Plisia na aktuálny stav a zúčtuj. Jedno miesto pre všetky tri cesty. */
export async function refreshPayment(paymentId: string): Promise<SettleResult | null> {
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
  if (!plisioEnabled()) return { checked: 0, credited: 0 };
  const admin = createServiceClient();
  const since = new Date(Date.now() - maxAgeHours * 3_600_000).toISOString();

  const { data: rows } = await admin
    .from(T)
    .select("payment_id, status")
    .eq("credited", false)
    .gte("created_at", since)
    .limit(100);

  let checked = 0;
  let credited = 0;
  for (const row of rows ?? []) {
    if (FINAL_STATUSES.has(String(row.status))) continue;
    const out = await refreshPayment(String(row.payment_id));
    if (!out) continue;
    checked += 1;
    if (out.credited) credited += 1;
  }
  return { checked, credited };
}

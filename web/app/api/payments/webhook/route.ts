import { NextResponse, type NextRequest } from "next/server";

import { refreshPayment, settlePermanentDeposit } from "@/lib/payments";
import { parsePlisioPayIn, plisioEnabled, verifyCallbackHash } from "@/lib/plisio";
import { createServiceClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Verejné — Plisio IPN callback. Plisio sem POSTne update pri každej zmene
 * stavu faktúry (`callback_url` posielame pri založení s `?json=true`).
 *
 * Telu sa NEVERÍ: vytiahne sa z neho len `txn_id` a skutočný stav sa doptá
 * Plisia naším secret kľúčom (`refreshPayment`). Podvrhnutý callback je tak
 * neškodný — spustí nanajvýš autoritatívnu kontrolu.
 *
 * Proti zneužitiu (cudzie POSTy roztáčajúce volania na Plisio API) chráni
 * lookup v našej DB: `txn_id`, ktoré nepatrí žiadnej OTVORENEJ platbe,
 * nespustí nič. `verify_hash` sa overuje len na logovanie — presný formát
 * hashu sa nedá reprodukovať bez reálneho callbacku a falošná negatíva by
 * zbytočne odkladala pripísanie na poller/cron.
 *
 * Vždy 200 — pravdu si čítame sami a zvyšok dotiahne cron reconciler.
 *
 * Route je zámerne mimo proxy matchera (`web/proxy.ts`): stroj-na-stroj
 * volanie bez session, kolo k Supabase Auth by bola zbytočná réžia.
 */
export async function POST(request: NextRequest) {
  if (!plisioEnabled()) return NextResponse.json({ ok: true });

  const raw = await request.text();

  let txnId = "";
  let isJson = false;
  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(raw) as Record<string, unknown>;
    isJson = true;
    txnId = String(payload.txn_id ?? payload.id ?? "");
  } catch {
    payload = Object.fromEntries(new URLSearchParams(raw));
    txnId = String(payload.txn_id ?? payload.id ?? "");
  }
  if (!txnId) return NextResponse.json({ ok: true, skipped: "no txn_id" });

  const callbackType = String(payload.ipn_type ?? payload.type ?? "").toLowerCase();
  if (callbackType === "pay_in") {
    // Unlike legacy invoices, a permanent transfer has no pre-created payment
    // row. A valid Plisio HMAC is therefore mandatory before any credit path.
    if (!isJson || !verifyCallbackHash(raw)) {
      console.warn("Rejected unsigned Plisio pay_in callback for", txnId);
      return NextResponse.json({ ok: false }, { status: 401 });
    }

    const deposit = parsePlisioPayIn(payload);
    if (!deposit) {
      return NextResponse.json({ ok: true, skipped: "incomplete pay_in" });
    }
    if (deposit.status !== "completed" && deposit.status !== "finished") {
      return NextResponse.json({ ok: true, skipped: deposit.status });
    }

    const settled = await settlePermanentDeposit(deposit);
    if (!settled) {
      console.error("Could not settle Plisio pay_in", txnId);
      // The cron reconciler independently scans completed pay-ins, so a 2xx
      // response avoids a provider retry storm while preserving recovery.
      return NextResponse.json({ ok: true, queued: true }, { status: 202 });
    }
    return NextResponse.json({ ok: true, credited: settled.credited });
  }

  // Len observabilita — pripísanie na podpise nikdy nestojí.
  if (isJson && !verifyCallbackHash(raw)) {
    console.warn("Plisio callback verify_hash mismatch for", txnId);
  }

  // Cudzie/neznáme txn_id skončí tu — žiadne volanie na Plisio.
  const admin = createServiceClient();
  const { data: row } = await admin
    .from("crypto_payments")
    .select("payment_id, credited")
    .eq("payment_id", txnId)
    .maybeSingle();
  if (!row) return NextResponse.json({ ok: true, skipped: "unknown payment" });

  if (!row.credited) await refreshPayment(txnId);

  return NextResponse.json({ ok: true });
}

import { NextResponse, type NextRequest } from "next/server";

import { refreshPayment } from "@/lib/payments";
import { plisioEnabled, verifyCallbackHash } from "@/lib/plisio";
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
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    isJson = true;
    txnId = String(data.txn_id ?? data.id ?? "");
  } catch {
    const form = Object.fromEntries(new URLSearchParams(raw));
    txnId = String(form.txn_id ?? form.id ?? "");
  }
  if (!txnId) return NextResponse.json({ ok: true, skipped: "no txn_id" });

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

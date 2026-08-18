import { NextResponse, type NextRequest } from "next/server";

import { onrampEnabled, paymentStatus } from "@/lib/onramp";
import { settlePayment } from "@/lib/payments";
import { createServiceClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Verejné — OnRamp callback. Služba sem spraví GET, keď je platba dokončená
 * (parametre value_coin, txid_in… pridáva k URL, ktorú sme dali wallet.php).
 *
 * Callback NIE JE podpísaný, preto sa mu neverí ani slovo:
 *   1. `pid` musí sedieť na NAŠU otvorenú onramp platbu (48 hex náhodných
 *      znakov — nedá sa uhádnuť ani vyskúšať),
 *   2. skutočný stav sa overí server-to-server cez payment-status.php
 *      (`provider_token` z založenia platby),
 *   3. pripísanie robí `settle_crypto_payment` — unique ledger, takže ani
 *      desať callbackov naraz nepripíše dvakrát.
 *
 * Parametre z query (sumy, txid) sa na rozhodovanie NEPOUŽÍVAJÚ — len sa
 * zalogujú pre prípadné dohľadanie na blockchaine.
 *
 * Vždy 200 — zvyšok dotiahne cron reconciler, rovnako ako pri Plisiu.
 */
export async function GET(request: NextRequest) {
  if (!onrampEnabled()) return NextResponse.json({ ok: true });

  const pid = request.nextUrl.searchParams.get("pid") ?? "";
  if (!pid.startsWith("onr_") || pid.length < 20) {
    return NextResponse.json({ ok: true, skipped: "no pid" });
  }

  const admin = createServiceClient();
  const { data: row } = await admin
    .from("crypto_payments")
    .select("payment_id, provider, provider_token, credited")
    .eq("payment_id", pid)
    .eq("provider", "onramp")
    .maybeSingle();
  if (!row) return NextResponse.json({ ok: true, skipped: "unknown" });
  if (row.credited) return NextResponse.json({ ok: true, already: true });

  const txidIn = request.nextUrl.searchParams.get("txid_in") ?? "";
  const valueForwarded = request.nextUrl.searchParams.get("value_forwarded_coin") ?? "";
  console.log(`OnRamp callback ${pid}: txid_in=${txidIn} forwarded=${valueForwarded}`);

  const status = await paymentStatus(String(row.provider_token ?? ""));
  if (status === "paid") {
    const out = await settlePayment(pid, "completed");
    return NextResponse.json({ ok: true, credited: Boolean(out?.credited) });
  }

  // Nezaplatené alebo nezistiteľné — len si poznač pohyb, cron to dotiahne.
  await admin
    .from("crypto_payments")
    .update({ status: "pending_confirm", updated_at: new Date().toISOString() })
    .eq("payment_id", pid)
    .eq("credited", false);
  return NextResponse.json({ ok: true, credited: false });
}

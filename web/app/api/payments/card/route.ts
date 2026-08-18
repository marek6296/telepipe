import { randomBytes } from "node:crypto";

import { NextResponse, type NextRequest } from "next/server";

import { customCoinsForUsd, customBonusPct } from "@/lib/coins";
import { siteUrl } from "@/lib/env";
import { checkoutUrl, createWallet, onrampEnabled } from "@/lib/onramp";
import { createServiceClient, getUser } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Platba kartou (OnRamp) — druhá cesta k Pipe Coinom popri krypte.
 *
 * POST { usd } — založí platbu a vráti checkout URL:
 *   1. vygeneruje sa neuhádnuteľné `payment_id` (to je zároveň jediný „kľúč"
 *      callbacku — OnRamp callbacky nie sú podpísané),
 *   2. `wallet.php` vráti zašifrovanú adresu checkoutu + `ipn_token`,
 *   3. riadok sa uloží do `crypto_payments` (provider='onramp') EŠTE PRED
 *      presmerovaním — bez riadku by nemal callback čo zúčtovať,
 *   4. klient ide na checkout v novom tabe; Billing medzitým polluje GET.
 *
 * GET ?pid=… — stav vlastnej platby pre prehliadač. Číta LEN našu DB: žiadne
 * volanie na OnRamp z pollingu, aby sa nedal roztáčať cudzími requestami.
 * Pravdu do DB dopĺňa callback a cron reconciler.
 *
 * Coiny sa počítajú z toho, čo si klient VYBRAL zaplatiť (vrátane objemového
 * bonusu) — nie z toho, koľko USDC po poplatkoch služby reálne dorazí. Kartové
 * poplatky sú náklad predaja; pri 2× multiplieri ich marža bez problémov nesie.
 */

const MIN_USD = 5;
const MAX_USD = 1_000;

export async function POST(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!onrampEnabled()) {
    return NextResponse.json({ error: "Card payments are not available right now." }, { status: 503 });
  }

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const usd = Math.round(Number(body.usd ?? 0) * 100) / 100;
  if (!Number.isFinite(usd) || usd < MIN_USD || usd > MAX_USD) {
    return NextResponse.json(
      { error: `Enter an amount between $${MIN_USD} and $${MAX_USD.toLocaleString("en-US")}.` },
      { status: 400 },
    );
  }

  // 24 bajtov náhody = 48 hex znakov. Toto id je jediné, čo callback pozná —
  // musí byť neuhádnuteľné, inak by si stav platby vedel „potvrdiť" ktokoľvek.
  // (Pripísanie aj tak stráži payment-status.php, ale prvá brána je táto.)
  const paymentId = `onr_${randomBytes(24).toString("hex")}`;
  const callback = `${siteUrl()}/api/payments/onramp?pid=${paymentId}`;

  const wallet = await createWallet(callback);
  if (!wallet.ok) {
    console.error("OnRamp wallet failed:", wallet.error);
    return NextResponse.json(
      { error: "Could not start the card payment. Try again in a minute." },
      { status: 502 },
    );
  }

  const coins = customCoinsForUsd(usd);
  const admin = createServiceClient();
  const { error } = await admin.from("crypto_payments").insert({
    payment_id: paymentId,
    account_id: user.id,
    account_email: user.email ?? "",
    order_number: paymentId,
    pack_id: `card-${usd.toFixed(2)}`,
    usd,
    coins,
    credit_usd: coins / 1000,
    provider: "onramp",
    provider_token: wallet.data.ipnToken,
    pay_currency: "USDC.POLYGON",
    pay_address: wallet.data.polygonAddressIn || "onramp",
    pay_amount: usd,
    status: "new",
  });
  if (error) {
    console.error("crypto_payments insert failed:", error.message);
    return NextResponse.json({ error: "Could not save the payment." }, { status: 500 });
  }

  return NextResponse.json({
    paymentId,
    url: checkoutUrl(wallet.data.addressIn, usd, user.email ?? ""),
    coins,
    bonusPct: customBonusPct(usd),
  });
}

export async function GET(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const pid = request.nextUrl.searchParams.get("pid") ?? "";
  if (!pid.startsWith("onr_")) {
    return NextResponse.json({ error: "Unknown payment." }, { status: 400 });
  }

  const admin = createServiceClient();
  const { data } = await admin
    .from("crypto_payments")
    .select("status, credited, coins")
    .eq("payment_id", pid)
    .eq("account_id", user.id)
    .maybeSingle();
  if (!data) return NextResponse.json({ error: "Unknown payment." }, { status: 404 });

  return NextResponse.json({
    status: String(data.status),
    credited: Boolean(data.credited),
    coins: Number(data.coins),
  });
}

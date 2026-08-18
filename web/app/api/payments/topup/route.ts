import { NextResponse, type NextRequest } from "next/server";

import {
  COINS_PER_USD,
  COIN_PACKS,
  CUSTOM_MAX_USD,
  CUSTOM_MIN_USD,
  customCoinsForUsd,
} from "@/lib/coins";
import { siteUrl } from "@/lib/env";
import { refreshPayment } from "@/lib/payments";
import { createInvoice, isPayCurrency, plisioEnabled } from "@/lib/plisio";
import { createServiceClient, getUser } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const T = "crypto_payments";

/**
 * POST — založ Plisio faktúru na balík Pipe Coinov.
 *
 * Balík aj kurz sa berú VÝHRADNE z `COIN_PACKS` (lib/coins.ts) — klient
 * posiela len id balíka a mincu, žiadne sumy. Coiny sa počítajú tu, pri
 * založení: keby sa medzitým zmenili bonusy, platba dostane, čo jej bolo
 * sľúbené. Pripísanie NIKDY nerobí táto route — iba `settle_crypto_payment`
 * po overení stavu u Plisia.
 */
export async function POST(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!plisioEnabled()) {
    return NextResponse.json(
      { error: "Crypto checkout is not available right now." },
      { status: 503 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const requestedId = String(body.packId ?? "");
  const pack = COIN_PACKS.find((item) => item.id === requestedId);

  // Balík z cenníka, alebo vlastná suma ("custom") — kurz a bonus počíta
  // VŽDY server z lib/coins.ts, klient posiela len číslo v USD.
  let packId: string;
  let usd: number;
  let coinsBought: number;
  let orderLabel: string;
  if (pack) {
    packId = pack.id;
    usd = pack.priceUsd;
    coinsBought = pack.coins;
    orderLabel = `${pack.name} pack`;
  } else if (requestedId === "custom") {
    // Na centy (napr. $8 alebo $8.50) — nie nasilu celé doláre.
    usd = Math.round(Number(body.customUsd) * 100) / 100;
    if (!Number.isFinite(usd) || usd < CUSTOM_MIN_USD || usd > CUSTOM_MAX_USD) {
      return NextResponse.json(
        { error: `Amount must be between $${CUSTOM_MIN_USD} and $${CUSTOM_MAX_USD}.` },
        { status: 400 },
      );
    }
    packId = "custom";
    coinsBought = customCoinsForUsd(usd);
    orderLabel = "Custom top-up";
  } else {
    return NextResponse.json({ error: "Unknown pack." }, { status: 400 });
  }

  const currency = String(body.currency ?? "").toUpperCase();
  if (!isPayCurrency(currency)) {
    return NextResponse.json({ error: "Unsupported currency." }, { status: 400 });
  }

  // `order_number` musí byť v Plisio store unikátny; UUID to rieši navždy.
  const orderNumber = `telepipe-${crypto.randomUUID()}`;
  // Callback s `?json=true` → Plisio pošle JSON + verify_hash (HMAC-SHA1).
  // `siteUrl()` namiesto request originu: webhook musí byť verejná produkčná
  // adresa aj keď faktúru založí niekto cez preview deployment.
  const callbackUrl = `${siteUrl()}/api/payments/webhook?json=true`;

  const invoice = await createInvoice({
    priceUsd: usd,
    currency,
    orderNumber,
    orderName: `Telepipe — ${orderLabel} (${coinsBought.toLocaleString("en-US")} Pipe Coins)`,
    email: user.email ?? "",
    callbackUrl,
  });
  if (!invoice.ok) {
    return NextResponse.json(
      { error: invoice.error || "Could not start the payment. Try another coin." },
      { status: 502 },
    );
  }

  const p = invoice.data;
  const admin = createServiceClient();
  const { error } = await admin.from(T).insert({
    payment_id: p.paymentId,
    account_id: user.id,
    account_email: user.email ?? "",
    order_number: orderNumber,
    pack_id: packId,
    usd,
    coins: coinsBought,
    // Jednotka v DB je USD — coiny sú prezentácia (lib/coins.ts).
    credit_usd: coinsBought / COINS_PER_USD,
    pay_currency: p.payCurrency,
    pay_address: p.payAddress,
    pay_amount: p.payAmount,
    qr_code: p.qrCode,
    invoice_url: p.invoiceUrl,
    status: p.status || "new",
    expire_at: p.expireAt,
  });
  // Faktúra existuje u Plisia, ale my o nej nemáme záznam → radšej ju
  // klientovi vôbec neukázať, než riskovať platbu, ktorú nevieme spárovať.
  if (error) {
    console.error("crypto_payments insert failed:", error.message);
    return NextResponse.json(
      { error: "Could not start the payment. Please try again." },
      { status: 500 },
    );
  }

  return NextResponse.json({
    paymentId: p.paymentId,
    payAddress: p.payAddress,
    payAmount: p.payAmount,
    payCurrency: p.payCurrency,
    qrCode: p.qrCode,
    invoiceUrl: p.invoiceUrl,
    expireAt: p.expireAt,
    status: p.status || "new",
    packId,
    usd,
    coins: coinsBought,
  });
}

/**
 * GET ?payment_id=… — stav platby pre checkout poller (každých 8 s).
 *
 * Kým platba nie je pripísaná, pri KAŽDOM ticku sa doptá Plisia a zúčtuje —
 * nie len pri zmene stavu. Zmeškaný webhook tak checkout dobehne sám.
 */
export async function GET(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const paymentId = request.nextUrl.searchParams.get("payment_id") ?? "";
  if (!paymentId) return NextResponse.json({ error: "Missing payment_id." }, { status: 400 });

  const admin = createServiceClient();
  const { data: row } = await admin
    .from(T)
    .select("payment_id, account_id, status, credited, coins, expire_at")
    .eq("payment_id", paymentId)
    .eq("account_id", user.id)
    .maybeSingle();
  if (!row) return NextResponse.json({ error: "Not found." }, { status: 404 });

  let status = String(row.status);
  let credited = Boolean(row.credited);

  if (!credited) {
    const out = await refreshPayment(paymentId);
    if (out?.found) {
      status = out.status ?? status;
      credited = out.credited;
    }
  }

  return NextResponse.json({
    status,
    credited,
    coins: Number(row.coins),
    expireAt: row.expire_at,
  });
}

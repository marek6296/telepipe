import QRCode from "qrcode";
import { NextResponse, type NextRequest } from "next/server";

import {
  createPermanentDepositAddress,
  isPayCurrency,
  plisioEnabled,
} from "@/lib/plisio";
import { createServiceClient, getUser } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const ADDRESS_TABLE = "crypto_deposit_addresses";
const EVENT_TABLE = "crypto_deposit_events";

type AddressRow = {
  pay_address: string;
  pay_currency: string;
  created_at: string;
};

async function qrForAddress(address: string): Promise<string> {
  return QRCode.toDataURL(address, {
    errorCorrectionLevel: "M",
    margin: 2,
    width: 440,
    color: { dark: "#0a0a0a", light: "#ffffff" },
  });
}

function addressResponse(row: AddressRow, qrCode: string) {
  return NextResponse.json({
    payAddress: row.pay_address,
    payCurrency: row.pay_currency,
    createdAt: row.created_at,
    qrCode,
    permanent: true,
  });
}

/**
 * POST { currency } — return (or create once) the signed-in account's
 * permanent Plisio deposit address for that cryptocurrency.
 */
export async function POST(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!plisioEnabled()) {
    return NextResponse.json(
      { error: "Crypto deposits are not available right now." },
      { status: 503 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const currency = String(body.currency ?? "").toUpperCase();
  if (!isPayCurrency(currency)) {
    return NextResponse.json({ error: "Unsupported currency." }, { status: 400 });
  }

  const admin = createServiceClient();
  const { data: existing, error: selectError } = await admin
    .from(ADDRESS_TABLE)
    .select("pay_address, pay_currency, created_at")
    .eq("account_id", user.id)
    .eq("pay_currency", currency)
    .maybeSingle();
  if (selectError) {
    console.error("crypto_deposit_addresses select failed:", selectError.message);
    return NextResponse.json({ error: "Could not load the deposit address." }, { status: 500 });
  }
  if (existing) {
    return addressResponse(existing as AddressRow, await qrForAddress(existing.pay_address));
  }

  const created = await createPermanentDepositAddress({
    depositUid: user.id,
    currency,
  });
  if (!created.ok) {
    console.error("Plisio permanent address failed:", created.error);
    return NextResponse.json(
      {
        error:
          "Could not create a permanent address. Make sure White-label deposits are enabled, then try again.",
      },
      { status: 502 },
    );
  }

  const { data: inserted, error: insertError } = await admin
    .from(ADDRESS_TABLE)
    .insert({
      account_id: user.id,
      deposit_uid: created.data.depositUid,
      pay_currency: created.data.payCurrency,
      pay_address: created.data.payAddress,
    })
    .select("pay_address, pay_currency, created_at")
    .single();

  if (!insertError && inserted) {
    return addressResponse(inserted as AddressRow, await qrForAddress(inserted.pay_address));
  }

  // Two tabs may request the same address simultaneously. The database unique
  // constraint picks one; return that row instead of surfacing a false error.
  const { data: raced } = await admin
    .from(ADDRESS_TABLE)
    .select("pay_address, pay_currency, created_at")
    .eq("account_id", user.id)
    .eq("pay_currency", currency)
    .maybeSingle();
  if (raced) {
    return addressResponse(raced as AddressRow, await qrForAddress(raced.pay_address));
  }

  console.error("crypto_deposit_addresses insert failed:", insertError?.message);
  return NextResponse.json({ error: "Could not save the deposit address." }, { status: 500 });
}

/**
 * GET ?after=<ISO>&currency=<cid> — lightweight browser poll. It only reads
 * our idempotent credit events; callbacks and the five-minute reconciler do
 * all provider communication and settlement.
 */
export async function GET(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const afterRaw = request.nextUrl.searchParams.get("after") ?? "";
  const afterDate = new Date(afterRaw);
  if (!afterRaw || Number.isNaN(afterDate.getTime())) {
    return NextResponse.json({ error: "Missing or invalid after timestamp." }, { status: 400 });
  }

  const currency = String(request.nextUrl.searchParams.get("currency") ?? "").toUpperCase();
  if (currency && !isPayCurrency(currency)) {
    return NextResponse.json({ error: "Unsupported currency." }, { status: 400 });
  }

  const admin = createServiceClient();
  let query = admin
    .from(EVENT_TABLE)
    .select("payment_id, pay_currency, source_usd, bonus_pct, coins, status, credited, created_at")
    .eq("account_id", user.id)
    .eq("credited", true)
    .gt("created_at", afterDate.toISOString())
    .order("created_at", { ascending: false })
    .limit(1);
  if (currency) query = query.eq("pay_currency", currency);

  const { data, error } = await query.maybeSingle();
  if (error) {
    console.error("crypto_deposit_events poll failed:", error.message);
    return NextResponse.json({ error: "Could not check the deposit." }, { status: 500 });
  }

  return NextResponse.json({ credited: Boolean(data), deposit: data ?? null });
}

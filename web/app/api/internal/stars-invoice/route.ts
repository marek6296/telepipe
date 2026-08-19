import { NextResponse, type NextRequest } from "next/server";
import { timingSafeEqual } from "node:crypto";

import { internalApiSecret } from "@/lib/env";
import { starPack } from "@/lib/stars";
import { createServiceClient } from "@/lib/supabase/server";
import { createInvoiceLink } from "@/lib/telegram-shop";

export const dynamic = "force-dynamic";

/**
 * Faktúra na Pipe Coiny pre control bota modelky.
 *
 * PREČO TENTO ENDPOINT VÔBEC EXISTUJE
 * -----------------------------------
 * Control bot je KLIENTOV bot — jeho token, jeho účet. Telegram Stars vždy
 * pristanú na tom botovi, ktorý faktúru vystavil. Keby si teda faktúru
 * vystavoval control bot, hviezdy by skončili u klienta a my by sme mu za ne
 * pripísali coiny zadarmo. Faktúru preto razí VÝHRADNE náš shop bot a control
 * bot dostane len odkaz, ktorý sa dá otvoriť.
 *
 * A PREČO CEZ WEB, A NIE PRIAMO Z WORKERA
 * ---------------------------------------
 * Cenník a tvar payloadu žijú v `lib/stars.ts`. Keby si ich worker počítal sám,
 * sú to dve pravdy o cene a raz sa rozídu — a rozídu sa ticho, lebo faktúru
 * nikto nekontroluje riadok po riadku. Worker sa preto pýta „daj faktúru pre
 * tento účet a tento balík" a rozhodnutie o cene ostáva na jednom mieste.
 */
export async function POST(request: NextRequest) {
  const secret = internalApiSecret();
  // Fail closed. Chýbajúce tajomstvo NIE JE „vývojový režim" — je to stav,
  // v ktorom endpoint nesmie vydať ani jednu faktúru.
  if (!secret) {
    console.error("stars-invoice: INTERNAL_API_SECRET nie je nastavené");
    return NextResponse.json({ error: "unavailable" }, { status: 503 });
  }
  if (!sameSecret(request.headers.get("x-internal-secret"), secret)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  let body: { accountId?: unknown; stars?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }

  const accountId = String(body.accountId ?? "");
  // Balík z whitelistu — počet hviezd chodí z workera, takže sa NIKDY nesmie
  // použiť priamo. Bez tejto kontroly by sa dala vypýtať faktúra na jednu
  // hviezdu a dostať coiny za celý balík.
  const pack = starPack(Math.round(Number(body.stars)));
  if (!/^[0-9a-f-]{36}$/.test(accountId) || !pack) {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }

  // Účet musí existovať a byť odomknutý. Zamknutému účtu nemá zmysel predávať
  // coiny, ktoré nemá ako minúť — a je to aj kontrola, že id nie je vymyslené.
  const supabase = createServiceClient();
  const { data: account } = await supabase
    .from("accounts")
    .select("id, plan, role")
    .eq("id", accountId)
    .maybeSingle();

  if (!account) {
    return NextResponse.json({ error: "unknown account" }, { status: 404 });
  }

  const url = await createInvoiceLink(accountId, pack);
  if (!url) {
    return NextResponse.json({ error: "invoice failed" }, { status: 502 });
  }

  return NextResponse.json({ url, stars: pack.stars, coins: pack.coins });
}

/** Porovnanie odolné voči časovaniu — dĺžku vyrovnáme, aby sa neprezradila. */
function sameSecret(given: string | null, expected: string): boolean {
  if (!given) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

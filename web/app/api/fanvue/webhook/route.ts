import { NextResponse, type NextRequest } from "next/server";

import { fanvueWebhookSecret } from "@/lib/env";
import { validSignature } from "@/lib/fanvue";
import { createServiceClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Jediná adresa pre všetky modelky. Rozdelí ich `creator.uuid` v tele.
 *
 * Port `simona-dashboard/app/api/fanvue/webhook/route.ts`. Sem chodia udalosti
 * z Fanvue. Tu sa nič nevymýšľa — správa sa overí a odloží do fronty
 * `fanvue_events`. Odpisuje až worker na Railway, ktorý si frontu vyberá.
 * Kratšia cesta by znamenala písať odpoveď v tejto požiadavke a Fanvue by
 * medzitým stihol doručenie vyhodnotiť ako neúspešné.
 *
 * Odpovedať treba rýchlo a takmer vždy 200 — pri chybe Fanvue doručenie opakuje
 * a po sérii zlyhaní si endpoint sám vypne. 401 je vyhradená pre zlý podpis:
 * tam opakovanie nemá čo zachrániť.
 *
 * Oproti predlohe sa podpis overuje PRED hľadaním modelky. Predloha držala
 * signing secret v riadku každej schémy a musela ju najprv nájsť; my máme jednu
 * Fanvue appku a teda jeden `FANVUE_WEBHOOK_SECRET` — neoverené telo sa tak
 * nikdy nedostane ani k dotazu do databázy.
 *
 * Route je zámerne mimo proxy matchera (`web/proxy.ts`): refresh session nemá
 * pre stroj-na-stroj volanie zmysel a len by pridal kolo k Supabase Auth.
 */
export async function POST(request: NextRequest) {
  // Telo sa musí čítať ako text. Preparsovaním a späť by sa podpis rozbil.
  const raw = await request.text();

  const secret = fanvueWebhookSecret();
  const signed = await validSignature(raw, request.headers.get("x-fanvue-signature"), secret);
  // Chýbajúci secret sem spadne tiež — bez neho nemáme čím overovať a
  // dôverovať komukoľvek, kto našiel našu adresu, je horšie než mlčať.
  if (!signed) return NextResponse.json({ error: "bad signature" }, { status: 401 });

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "bad body" }, { status: 400 });
  }

  const data = (body.data ?? {}) as Record<string, unknown>;
  const creator = (data.creator ?? {}) as Record<string, unknown>;
  const creatorUuid = String(creator.uuid ?? data.recipientUuid ?? "");
  if (!creatorUuid) return NextResponse.json({ ok: true, skipped: "no creator uuid" });

  const eventId = String(body.id ?? body.eventId ?? "");
  const type = String(body.type ?? "");
  if (!eventId || !type) return NextResponse.json({ ok: true, skipped: "no id or type" });

  // Smerovanie: unikátny index `fanvue_creator_idx` zaručuje, že jeden Fanvue
  // účet patrí najviac jednej modelke.
  const admin = createServiceClient();
  const { data: row } = await admin
    .from("fanvue")
    .select("model_id")
    .eq("creator_uuid", creatorUuid)
    .maybeSingle();

  // Neznámy účet — nemáme kam to uložiť, ale opakovať netreba.
  if (!row) return NextResponse.json({ ok: true, skipped: "unknown account" });

  const { error } = await admin.from("fanvue_events").insert({
    model_id: row.model_id as string,
    event_id: eventId,
    event_type: type,
    payload: body,
  });

  // 23505 = to isté doručenie sme už raz dostali. Fanvue opakuje, my nie.
  if (error && error.code !== "23505") {
    console.error("Fanvue event could not be queued:", error.message);
    return NextResponse.json({ error: "queue failed" }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}

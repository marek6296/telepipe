import { NextResponse } from "next/server";

import { attributedLink } from "@/lib/checkout";
import { createServiceClient } from "@/lib/supabase/server";

/**
 * Krátky odkaz z chatu: zapíš klik a pošli ho na stránku modelky.
 *
 * PREČO CEZ NÁS. Jedenásť ľudí dostalo odkaz a nula zaplatila — a nedalo sa
 * zistiť, ktorá polovica je pokazená. „Nikto neklikol" a „klikli a nekúpili"
 * sú dve opačné diagnózy a robí sa proti nim opak. Toto je jediné miesto, kde
 * sa tá informácia dá získať.
 *
 * CIEĽ SA ČÍTA AŽ TERAZ, nie pri odoslaní odkazu. Vďaka tomu odkaz poslaný
 * minulý týždeň funguje aj po tom, ako si klient stránku premenuje — a nemáme
 * dve miesta, kde by mohla žiť iná adresa.
 *
 * KEĎ NIEČO ZLYHÁ, ČLOVEK SA MUSÍ DOSTAŤ ĎALEJ. Fanúšik, ktorý práve klikol, je
 * to najcennejšie, čo v lieviku máme; nesmie skončiť na chybovej stránke preto,
 * že sa nepodaril zápis štatistiky. Preto sa najprv presmeruje a merania sú
 * `best effort`.
 *
 * Neplatný token vedie na hlavnú stránku, nie na 404: odkaz mohol byť
 * prepísaný ručne alebo skrátený mailovým klientom.
 */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  const home = new URL("/", process.env.NEXT_PUBLIC_SITE_URL ?? "https://telepipe.me");

  // Token je náš, generovaný z úzkej abecedy — čokoľvek iné je odpad a nemá
  // zmysel s tým chodiť do databázy.
  if (!/^[A-Za-z0-9]{4,32}$/.test(token ?? "")) {
    return NextResponse.redirect(home, 302);
  }

  const supabase = createServiceClient();
  const { data: link } = await supabase
    .from("short_links")
    .select("token, model_id, tg_id, clicks")
    .eq("token", token)
    .maybeSingle();

  if (!link) return NextResponse.redirect(home, 302);

  const { data: persona } = await supabase
    .from("persona")
    .select("cta_link")
    .eq("model_id", link.model_id)
    .maybeSingle();

  const target = attributedLink(String(persona?.cta_link ?? ""), Number(link.tg_id));
  const destination = target || home.toString();

  const now = new Date().toISOString();
  // Poradie je zámerné: presmerovanie sa pripraví, zápisy sú best effort a
  // nesmú človeka zdržať ani zhodiť.
  await Promise.allSettled([
    supabase
      .from("short_links")
      .update({
        clicks: Number(link.clicks ?? 0) + 1,
        last_click_at: now,
        ...(Number(link.clicks ?? 0) === 0 ? { first_click_at: now } : {}),
      })
      .eq("token", token),
    // Worker si to prečíta a majiteľovi príde „práve otvoril tvoju stránku".
    supabase
      .from("dm_users")
      .update({ link_clicked_at: now })
      .eq("model_id", link.model_id)
      .eq("tg_id", link.tg_id),
  ]);

  const response = NextResponse.redirect(destination, 302);
  // Bez tohto by prehliadač presmerovanie zacacheoval a druhý klik by sa
  // nikdy nezapočítal.
  response.headers.set("Cache-Control", "no-store, max-age=0");
  return response;
}

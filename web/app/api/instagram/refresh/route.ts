import { NextResponse, type NextRequest } from "next/server";

import { decrypt, encrypt } from "@/lib/crypto";
import { cronSecret, encryptionKey } from "@/lib/env";
import { refreshToken } from "@/lib/instagram";
import { createServiceClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

/**
 * Predĺženie Instagram tokenov (Vercel cron, `web/vercel.json`).
 *
 * PREČO TO MUSÍ EXISTOVAŤ. Dlhodobý token platí 60 dní a obnoviť sa dá LEN kým
 * je platný — token, ktorý sa 60 dní neobnovil, je nenávratne mŕtvy a klient sa
 * musí pripájať nanovo. Bez tohto by modelka dva mesiace po pripojení prestala
 * odpisovať a vyzeralo by to ako náhodná porucha.
 *
 * Obnovuje sa s rezervou (`PRAH_DNI`), nie na poslednú chvíľu: jeden výpadok
 * Mety v deň expirácie by inak stál pripojenie. Meta zároveň odmieta obnoviť
 * token mladší než 24 hodín, takže čerstvo pripojené účty sa preskakujú samy —
 * ich `token_expires_at` je ďaleko.
 *
 * Zlyhanie jedného účtu nesmie zastaviť ostatné: dôvod sa zapíše do
 * `last_error`, aby ho klient videl na karte, a ide sa ďalej.
 */
const PRAH_DNI = 14;

function authorized(request: NextRequest): boolean {
  const secret = cronSecret();
  if (!secret) return true; // nenakonfigurované (dev) → povoliť
  if (request.headers.get("authorization") === `Bearer ${secret}`) return true;
  if (request.nextUrl.searchParams.get("secret") === secret) return true;
  return false;
}

export async function GET(request: NextRequest) {
  if (!authorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const admin = createServiceClient();
  const hranica = new Date(Date.now() + PRAH_DNI * 86_400_000).toISOString();

  const { data, error } = await admin
    .from("instagram")
    .select("model_id, access_token_enc, token_expires_at")
    .eq("connected", true)
    .lt("token_expires_at", hranica);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const kluc = encryptionKey();
  let obnovene = 0;
  const zlyhania: string[] = [];

  for (const row of data ?? []) {
    const modelId = String(row.model_id);
    try {
      const stary = await decrypt(String(row.access_token_enc ?? ""), kluc);
      if (!stary) throw new Error("no stored token");

      const novy = await refreshToken(stary);
      await admin
        .from("instagram")
        .update({
          access_token_enc: await encrypt(novy.accessToken, kluc),
          token_expires_at: new Date(Date.now() + novy.expiresIn * 1000).toISOString(),
          last_error: "",
          updated_at: new Date().toISOString(),
        })
        .eq("model_id", modelId);
      obnovene += 1;
    } catch (err) {
      const dovod = err instanceof Error ? err.message : String(err);
      zlyhania.push(modelId);
      // Klient to musí vidieť na karte — inak sa o mŕtvom pripojení dozvie tým,
      // že mu prestane odpisovať agent.
      await admin
        .from("instagram")
        .update({ last_error: dovod.slice(0, 400), updated_at: new Date().toISOString() })
        .eq("model_id", modelId);
    }
  }

  return NextResponse.json({ ok: true, kontrolovanych: data?.length ?? 0, obnovene, zlyhania });
}

import { NextResponse, type NextRequest } from "next/server";

import { encrypt } from "@/lib/crypto";
import { encryptionKey } from "@/lib/env";
import { exchangeCode, whoami } from "@/lib/fanvue";
import { getModel, requireUser } from "@/lib/models";
import { createServiceClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Návrat z Fanvue: kód sa vymení za tokeny a účet je pripojený.
 *
 * Port `simona-dashboard/app/api/fanvue/callback/route.ts`. Chyby sa nevyhadzujú
 * na obrazovku ako pád aplikácie — vrátia sa späť na kartu ako text v adrese,
 * nech je vidno, čo sa pokazilo.
 *
 * Vlastníctvo sa overuje ZNOVA (cookie `fv_model` je len údaj z prehliadača) a
 * zápis ide service kľúčom, lebo na `*_enc` stĺpce `authenticated` grant nemá.
 * Preto je pri update aj `eq("model_id", …)` po tom, čo RLS-ový `getModel`
 * potvrdil, že modelka patrí prihlásenému.
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const jar = request.cookies;
  const modelId = jar.get("fv_model")?.value ?? "";

  const back = (msg: string) =>
    NextResponse.redirect(
      new URL(
        modelId
          ? `/app/m/${modelId}/fanvue?error=${encodeURIComponent(msg)}`
          : "/app/models",
        request.nextUrl.origin,
      ),
    );

  await requireUser();

  const denied = params.get("error");
  if (denied) return back(params.get("error_description") || denied);

  const code = params.get("code");
  const state = params.get("state");
  const verifier = jar.get("fv_verifier")?.value;
  const expected = jar.get("fv_state")?.value;

  if (!code || !verifier || !expected || state !== expected || !modelId) {
    return back("We could not verify that sign-in. Please try again.");
  }

  const model = await getModel(modelId);
  if (!model) return back("Model not found.");

  try {
    const tokens = await exchangeCode(request.nextUrl.origin, code, verifier);
    const me = await whoami(tokens.access_token);
    const key = encryptionKey();

    const admin = createServiceClient();
    const { error } = await admin.from("fanvue").upsert(
      {
        model_id: model.id,
        connected: true,
        access_token_enc: await encrypt(tokens.access_token, key),
        refresh_token_enc: tokens.refresh_token
          ? await encrypt(tokens.refresh_token, key)
          : "",
        expires_at: new Date(Date.now() + (tokens.expires_in ?? 3600) * 1000).toISOString(),
        scope: tokens.scope ?? "",
        creator_uuid: me.uuid ?? "",
        handle: me.handle ?? "",
        display_name: me.displayName ?? "",
        last_error: "",
        updated_at: new Date().toISOString(),
      },
      { onConflict: "model_id" },
    );
    if (error) {
      // Unikátny index na `creator_uuid` — ten istý Fanvue účet už visí na inej
      // modelke. Webhook by inak nevedel, komu udalosť patrí.
      if (error.code === "23505") {
        return back("That Fanvue account is already connected to another model.");
      }
      return back(error.message);
    }
  } catch (err) {
    return back(err instanceof Error ? err.message : String(err));
  }

  const done = NextResponse.redirect(
    new URL(`/app/m/${model.id}/fanvue`, request.nextUrl.origin),
  );
  for (const name of ["fv_verifier", "fv_state", "fv_model"]) done.cookies.delete(name);
  return done;
}

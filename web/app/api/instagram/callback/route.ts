import { NextResponse, type NextRequest } from "next/server";

import { getViewerRole } from "@/lib/admin";
import { encrypt } from "@/lib/crypto";
import { encryptionKey } from "@/lib/env";
import { configId, exchangeCode, profile } from "@/lib/instagram";
import { getModel } from "@/lib/models";
import { createServiceClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Unified Login: kód → Business Integration System User token → priradený Instagram účet.
 *
 * Chyby sa nevyhadzujú na obrazovku ako pád aplikácie — vrátia sa späť na kartu
 * ako text v adrese, nech je vidno, čo sa pokazilo. Klient, ktorý sa nepripojil,
 * potrebuje vedieť prečo.
 *
 * Token bez expirácie sa ukladá s NULL; neobnovuje sa Instagram refresh endpointom.
 *
 * Vlastníctvo sa overuje ZNOVA (cookie `ig_model` je len údaj z prehliadača) a
 * zápis ide service kľúčom, lebo na `access_token_enc` a `connected` klient
 * grant nemá — a mať nesmie.
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const jar = request.cookies;
  const modelId = jar.get("ig_model")?.value ?? "";

  const back = (msg: string) =>
    NextResponse.redirect(
      new URL(
        modelId
          ? `/app/m/${modelId}/instagram?error=${encodeURIComponent(msg)}`
          : "/app/models",
        request.nextUrl.origin,
      ),
    );

  const rola = await getViewerRole();
  if (rola !== "superadmin") {
    return NextResponse.redirect(new URL("/app/models", request.nextUrl.origin));
  }

  // Používateľ klikol „Cancel" — to nie je chyba, len sa nič nestalo.
  const error = params.get("error");
  if (error) {
    return back(params.get("error_description") || error);
  }

  const state = params.get("state") ?? "";
  const ocakavany = jar.get("ig_state")?.value ?? "";
  if (!state || state !== ocakavany) {
    return back("The login did not come back from us. Try connecting again.");
  }

  const code = params.get("code") ?? "";
  if (!code) return back("Instagram sent no authorization code.");

  const model = modelId ? await getModel(modelId) : null;
  if (!model) return back("That model is not yours.");

  try {
    const kratky = await exchangeCode(request.nextUrl.origin, code);
    const me = await profile(kratky.accessToken);

    const admin = createServiceClient();
    const { error: dbError } = await admin.from("instagram").upsert(
      {
        model_id: model.id,
        connected: true,
        access_token_enc: await encrypt(kratky.accessToken, encryptionKey()),
        token_expires_at: kratky.expiresIn > 0 ? new Date(Date.now() + kratky.expiresIn * 1000).toISOString() : null,
        token_type: "unified",
        client_business_id: me.businessId,
        login_config_id: configId(),
        scope: kratky.permissions,
        ig_user_id: me.id,
        username: me.username,
        account_type: me.accountType,
        last_error: "",
        connected_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      { onConflict: "model_id" },
    );
    if (dbError) return back(dbError.message);
  } catch (err) {
    return back(err instanceof Error ? err.message : String(err));
  }

  const response = NextResponse.redirect(
    new URL(`/app/m/${model.id}/instagram?connected=1`, request.nextUrl.origin),
  );
  response.cookies.delete("ig_state");
  response.cookies.delete("ig_model");
  return response;
}

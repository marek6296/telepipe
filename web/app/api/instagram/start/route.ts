import { NextResponse, type NextRequest } from "next/server";

import { getViewerRole } from "@/lib/admin";
import { authorizeUrl, randomToken } from "@/lib/instagram";
import { getModel, requireUser } from "@/lib/models";

export const dynamic = "force-dynamic";

/**
 * Začiatok pripojenia: pošle majiteľa na Instagram.
 *
 * ZAMKNUTÉ NA SUPERADMINA. Karta Instagram je zatiaľ len na testovanie a
 * neviditeľné tlačidlo nie je hranica — cudzí účet by si adresu vedel napísať
 * do prehliadača sám. Preto sa rola overuje aj tu, nielen v UI.
 *
 * `state` v cookie je jediné, čo pri návrate dokazuje, že sa vracia NAŠE
 * prihlásenie a nie niekoho cudzí odkaz. Cookie žije desať minút; `ig_model`
 * drží, ku ktorej modelke sa účet pripája (callback si vlastníctvo overí ešte raz).
 */
export async function GET(request: NextRequest) {
  await requireUser();

  const rola = await getViewerRole();
  if (rola !== "superadmin") {
    return NextResponse.redirect(new URL("/app/models", request.nextUrl.origin));
  }

  const modelId = request.nextUrl.searchParams.get("model") ?? "";
  const model = modelId ? await getModel(modelId) : null;
  if (!model) {
    return NextResponse.redirect(new URL("/app/models", request.nextUrl.origin));
  }

  const back = (msg: string) =>
    NextResponse.redirect(
      new URL(
        `/app/m/${model.id}/instagram?error=${encodeURIComponent(msg)}`,
        request.nextUrl.origin,
      ),
    );

  const state = randomToken();
  let target: string;
  try {
    target = authorizeUrl(request.nextUrl.origin, state);
  } catch (err) {
    // Chýbajúce INSTAGRAM_APP_* nie je pád aplikácie — vráť to na kartu ako text.
    return back(err instanceof Error ? err.message : String(err));
  }

  const response = NextResponse.redirect(target);
  const options = {
    httpOnly: true,
    sameSite: "lax" as const,
    path: "/",
    maxAge: 600,
    secure: process.env.NODE_ENV === "production",
  };
  response.cookies.set("ig_state", state, options);
  response.cookies.set("ig_model", model.id, options);
  return response;
}

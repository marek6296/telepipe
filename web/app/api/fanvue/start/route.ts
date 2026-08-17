import { NextResponse, type NextRequest } from "next/server";

import { authorizeUrl, randomToken } from "@/lib/fanvue";
import { getModel, requireUser } from "@/lib/models";

export const dynamic = "force-dynamic";

/**
 * Začiatok pripojenia: pošle majiteľa na Fanvue.
 *
 * Port `simona-dashboard/app/api/fanvue/start/route.ts`. Rozdiel oproti
 * predlohe: tam bola modelka daná session-ou (`myModel`), tu ju treba overiť
 * proti prihlásenému účtu — `getModel` ide cez RLS, takže cudzie id vráti null.
 *
 * Náhodný `verifier` a `state` ostávajú v cookie a Fanvue ich nikdy nevidí — pri
 * návrate sa podľa nich overí, že sa vracia naozaj naše prihlásenie. Cookie žije
 * desať minút, čo je na jedno prekliknutie viac než dosť. `fv_model` drží, ku
 * ktorej modelke sa účet pripája (callback si vlastníctvo overí ešte raz).
 */
export async function GET(request: NextRequest) {
  await requireUser();

  const modelId = request.nextUrl.searchParams.get("model") ?? "";
  const model = modelId ? await getModel(modelId) : null;
  if (!model) {
    return NextResponse.redirect(new URL("/app/models", request.nextUrl.origin));
  }

  const back = (msg: string) =>
    NextResponse.redirect(
      new URL(
        `/app/m/${model.id}/fanvue?error=${encodeURIComponent(msg)}`,
        request.nextUrl.origin,
      ),
    );

  const verifier = randomToken();
  const state = randomToken();

  let target: string;
  try {
    target = await authorizeUrl(request.nextUrl.origin, state, verifier);
  } catch (err) {
    // Chýbajúce FANVUE_CLIENT_* nie je pád aplikácie — vráť to na kartu ako text.
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
  response.cookies.set("fv_verifier", verifier, options);
  response.cookies.set("fv_state", state, options);
  response.cookies.set("fv_model", model.id, options);
  return response;
}

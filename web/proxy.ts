import type { NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

// Next 16 premenoval `middleware.ts` na `proxy.ts` — funkcionalita je rovnaká.
export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Preskakujeme statické assety a obrázky — session refresh tam nedáva zmysel.
  // `api/fanvue/webhook` je stroj-na-stroj volanie od Fanvue: žiadna session,
  // a Fanvue čaká odpoveď v sekundách, takže kolo navyše k Supabase Auth je
  // zbytočná réžia. Autentikuje sa podpisom tela, nie cookie.
  matcher: [
    "/((?!_next/static|_next/image|api/fanvue/webhook|favicon.ico|icon.png|logo-white.png|logo-black.png|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2?)$).*)",
  ],
};

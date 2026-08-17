import type { NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

// Next 16 premenoval `middleware.ts` na `proxy.ts` — funkcionalita je rovnaká.
export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Preskakujeme statické assety a obrázky — session refresh tam nedáva zmysel
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|icon.png|logo-white.png|logo-black.png|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2?)$).*)",
  ],
};

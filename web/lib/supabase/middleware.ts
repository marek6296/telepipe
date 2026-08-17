import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";

/** Cesty prístupné bez prihlásenia. */
const PUBLIC_PREFIXES = [
  // Marketing — `/` rieši `isPublicPath` zvlášť (presná zhoda)
  "/features",
  "/how-it-works",
  "/pricing",
  // Auth
  "/login",
  "/register",
  "/reset-password",
  "/update-password",
  "/auth",
  "/api",
];

function isPublicPath(pathname: string): boolean {
  if (pathname === "/") return true;
  return PUBLIC_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Refresh session cookies + guard na `/app/**`.
 *
 * Pozor na poradie: `NextResponse.next({ request })` sa musí vytvárať ZNOVU
 * vždy keď Supabase nastaví cookies, inak sa refreshnutý token stratí.
 */
export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl(), supabaseAnonKey(), {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // getUser() validuje token u Supabase — nutné volať, inak sa session nerefreshne
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  // Neprihlásený na chránenej ceste → /login s návratovou adresou
  if (!user && !isPublicPath(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  // Prihlásený na auth stránke → rovno do appky
  if (user && (pathname === "/login" || pathname === "/register")) {
    const url = request.nextUrl.clone();
    url.pathname = "/app";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}

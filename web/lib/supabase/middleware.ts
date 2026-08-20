import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";

/** Verejné marketingové cesty, ktoré nepotrebujú ani refresh session. */
const MARKETING_PREFIXES = [
  "/features",
  "/how-it-works",
  "/pricing",
  "/telegram-ai-chatbot",
  "/telegram-automation",
  "/ai-chatter",
  "/ai-model-chatbot",
  "/fanvue-ai-chatbot",
  "/ai-chatbot-for-creators",
  "/ai-chatbot-for-model-agencies",
  "/virtual-number-for-telegram",
  "/guides",
  // Právne stránky MUSIA byť verejné. Privacy Policy schovaná za loginom je
  // bezcenná — číta ju aj fanúšik, ktorý u nás nemá účet a nikdy mať nebude.
  "/privacy",
  "/terms",
  "/contact",
] as const;

/** Metadata a discovery súbory musia crawlerovi odpovedať bez auth roundtripu. */
const DISCOVERY_PATHS = [
  "/robots.txt",
  "/sitemap.xml",
  "/llms.txt",
  "/2ea2aec9a95c703b90f73a028dabbb6a.txt",
] as const;

/** Cesty prístupné bez prihlásenia. */
const PUBLIC_PREFIXES = [
  ...MARKETING_PREFIXES,
  ...DISCOVERY_PATHS,
  // Auth
  "/login",
  "/register",
  "/reset-password",
  "/update-password",
  "/auth",
  "/api",
  // Krátke odkazy z chatu. Klikajú na ne FANÚŠIKOVIA modeliek — ľudia, ktorí
  // u nás nemajú účet a nikdy mať nebudú. Za loginom by presmerovanie skončilo
  // na našej prihlasovacej stránke a odkaz by neposlal nikoho nikam.
  "/r",
];

function isPublicPath(pathname: string): boolean {
  if (pathname === "/") return true;
  return PUBLIC_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function isSessionFreePath(pathname: string): boolean {
  if (pathname === "/") return true;
  // `/r` je tu tiež: presmerovanie nepotrebuje session a čítanie cookies by mu
  // len pridalo roundtrip v ceste, ktorá má byť čo najkratšia.
  return [...MARKETING_PREFIXES, ...DISCOVERY_PATHS, "/r"].some(
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
  const { pathname } = request.nextUrl;

  // Verejné statické stránky nepoužívajú session. Vynechanie vzdialeného
  // `getUser()` znižuje TTFB pre ľudí aj crawlery bez zmeny app auth toku.
  if (isSessionFreePath(pathname)) {
    return NextResponse.next({ request });
  }

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

  // Neprihlásený na chránenej ceste → /login s návratovou adresou.
  // Query string ide s ňou — checkout z cenníka nesie `?pack=…` a bez neho by
  // klient po prihlásení pristál v checkoute bez predvybraného balíka.
  if (!user && !isPublicPath(pathname)) {
    const url = request.nextUrl.clone();
    const next = pathname + request.nextUrl.search;
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", next);
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

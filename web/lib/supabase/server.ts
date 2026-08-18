import { cache } from "react";
import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { createClient as createSupabaseClient } from "@supabase/supabase-js";

import { supabaseAnonKey, supabaseServiceKey, supabaseUrl } from "@/lib/env";

/**
 * User-scoped klient pre server komponenty a server actions.
 * Session sa číta z cookies, dáta chráni RLS — toto je náš default.
 */
export async function createClient(options?: { rememberMe?: boolean }) {
  const cookieStore = await cookies();

  return createServerClient(supabaseUrl(), supabaseAnonKey(), {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options: cookieOptions } of cookiesToSet) {
            // „Keep me signed in" vypnuté ⇒ session cookie (zmizne po zatvorení
            // prehliadača). Inak necháme Supabase expiráciu tak ako ju poslala.
            const finalOptions =
              options?.rememberMe === false
                ? { ...cookieOptions, maxAge: undefined, expires: undefined }
                : cookieOptions;
            cookieStore.set(name, value, finalOptions);
          }
        } catch {
          // Volané zo server komponentu — cookies sa dajú zapisovať len v akcii
          // alebo route handleri. Refresh session zabezpečí proxy.ts.
        }
      },
    },
  });
}

/**
 * Vráti prihláseného používateľa alebo null. Vždy `getUser()` (overuje token
 * u Supabase), nikdy nie `getSession()` — tá číta cookie bez validácie.
 */
export const getUser = cache(async function getUser() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
});

/**
 * Service-role klient — OBCHÁDZA RLS. Používať výhradne v server actions, ktoré
 * si samy overia vlastníctvo (napr. zápis do `*_enc` stĺpcov, na ktoré rola
 * `authenticated` nemá column grant). Nikdy neexportovať do client komponentu.
 */
export function createServiceClient() {
  return createSupabaseClient(supabaseUrl(), supabaseServiceKey(), {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

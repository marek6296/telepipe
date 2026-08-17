import { createBrowserClient } from "@supabase/ssr";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";

/**
 * Klient pre prehliadač (client komponenty) — anon kľúč + session z cookies.
 * Všetky dáta chráni RLS z migrácie 007.
 */
export function createClient() {
  return createBrowserClient(supabaseUrl(), supabaseAnonKey());
}

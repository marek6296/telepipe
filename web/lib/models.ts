import { notFound, redirect } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/server";
import { toNumber } from "@/lib/format";

/**
 * Serverové čítanie klientských dát. VŽDY user-scoped klientom — RLS z migrácie
 * 007 je jediná obrana, service key sa tu nesmie objaviť.
 *
 * POZOR: `select('*')` na `models`, `behavior`, `voice_jobs` a `tg_login_jobs`
 * skončí chybou „permission denied for column…" — rola `authenticated` má na
 * týchto tabuľkách len column-scoped grant. Stĺpce preto vymenúvame ručne.
 */

export const MODEL_COLUMNS =
  "id, account_id, name, status, status_reason, claimed_by, heartbeat_at, " +
  "tg_api_id, tg_api_hash, owner_chat_id, owner_as_client, voice_only_ids, " +
  "created_at, updated_at";

export type ModelRow = {
  id: string;
  account_id: string;
  name: string;
  status: string;
  status_reason: string;
  claimed_by: string | null;
  heartbeat_at: string | null;
  tg_api_id: number | null;
  tg_api_hash: string;
  owner_chat_id: number | null;
  owner_as_client: boolean;
  voice_only_ids: number[];
  created_at: string;
  updated_at: string;
};

export type AccountRow = {
  id: string;
  email: string;
  credit_balance_usd: string | number;
  created_at: string;
  /** Migrácia 009 — rola rozhoduje o admin sekcii, plán je zatiaľ len štítok. */
  role: string;
  plan: string;
};

/** Modelka + čísla, ktoré chce klient vidieť na karte. */
export type ModelStats = {
  chats: number;
  converted: number;
  spentToday: number;
};

/** Prihlásený používateľ, inak redirect na login (layout `/app` to už rieši). */
export async function requireUser(): Promise<User> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  return user;
}

export async function getAccount(): Promise<AccountRow | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("accounts")
    .select("id, email, credit_balance_usd, created_at, role, plan")
    .maybeSingle();
  return (data as AccountRow | null) ?? null;
}

export async function listModels(): Promise<ModelRow[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("models")
    .select(MODEL_COLUMNS)
    .order("created_at", { ascending: true });

  if (error) throw new Error(`Could not load your models: ${error.message}`);
  return (data ?? []) as unknown as ModelRow[];
}

/** Modelka podľa id — RLS zabezpečí, že cudziu nikdy nevráti. */
export async function getModel(id: string): Promise<ModelRow | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("models")
    .select(MODEL_COLUMNS)
    .eq("id", id)
    .maybeSingle();
  return (data as unknown as ModelRow | null) ?? null;
}

/** Ako `getModel`, ale cudzie/neexistujúce id je 404 (nie prázdna stránka). */
export async function requireModel(id: string): Promise<ModelRow> {
  const model = await getModel(id);
  if (!model) notFound();
  return model;
}

/** Polnoc UTC — spotreba „za dnes" musí byť rovnaká pre server aj klienta. */
function startOfUtcDay(): string {
  const now = new Date();
  return new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  ).toISOString();
}

/**
 * Štatistiky pre zoznam modeliek. Počty ťaháme cez `head: true` (server vráti
 * len Content-Range, nie riadky) — pri konverzácii s tisíckami fanúšikov by
 * sťahovanie celej tabuľky bolo zbytočné.
 */
export async function getModelStats(
  modelIds: string[],
): Promise<Record<string, ModelStats>> {
  const stats: Record<string, ModelStats> = {};
  for (const id of modelIds) {
    stats[id] = { chats: 0, converted: 0, spentToday: 0 };
  }
  if (modelIds.length === 0) return stats;

  const supabase = await createClient();

  const counts = await Promise.all(
    modelIds.map(async (id) => {
      const [all, converted] = await Promise.all([
        supabase
          .from("dm_users")
          .select("tg_id", { count: "exact", head: true })
          .eq("model_id", id),
        supabase
          .from("dm_users")
          .select("tg_id", { count: "exact", head: true })
          .eq("model_id", id)
          .eq("funnel_stage", "converted"),
      ]);
      return { id, chats: all.count ?? 0, converted: converted.count ?? 0 };
    }),
  );

  for (const row of counts) {
    stats[row.id].chats = row.chats;
    stats[row.id].converted = row.converted;
  }

  // charged_usd = čo platí klient. `atlas_cost_usd` (naša nákupná cena) sa do
  // klientského UI nesmie dostať nikdy.
  const { data: usage } = await supabase
    .from("usage_events")
    .select("model_id, charged_usd")
    .gte("created_at", startOfUtcDay());

  for (const event of usage ?? []) {
    const bucket = stats[event.model_id as string];
    if (bucket) bucket.spentToday += toNumber(event.charged_usd as string);
  }

  return stats;
}

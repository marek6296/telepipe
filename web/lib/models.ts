import { cache } from "react";
import { notFound, redirect } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { isUnlocked } from "@/lib/access";
import { createClient, getUser } from "@/lib/supabase/server";
import { toNumber } from "@/lib/format";
import {
  modelTypeHasSubTab,
  modelTypeHasTab,
  tabIsSuperadminOnly,
  type ModelSubTabSlug,
  type ModelTabSlug,
} from "@/lib/model-types";

/**
 * Serverové čítanie klientských dát. VŽDY user-scoped klientom — RLS z migrácie
 * 007 je jediná obrana, service key sa tu nesmie objaviť.
 *
 * POZOR: `select('*')` na `models`, `behavior`, `voice_jobs` a `tg_login_jobs`
 * skončí chybou „permission denied for column…" — rola `authenticated` má na
 * týchto tabuľkách len column-scoped grant. Stĺpce preto vymenúvame ručne.
 */

export const MODEL_COLUMNS =
  "id, account_id, name, model_type, status, status_reason, claimed_by, heartbeat_at, " +
  "tg_api_id, tg_api_hash, owner_chat_id, owner_as_client, voice_only_ids, " +
  "skip_contacts, contact_exceptions, setup_mode, created_at, updated_at";

export type ModelRow = {
  id: string;
  account_id: string;
  name: string;
  /** Typ agenta (migrácia 018). Význam a mapa na taby: `lib/model-types.ts`. */
  model_type: string;
  status: string;
  status_reason: string;
  claimed_by: string | null;
  heartbeat_at: string | null;
  tg_api_id: number | null;
  tg_api_hash: string;
  owner_chat_id: number | null;
  owner_as_client: boolean;
  voice_only_ids: number[];
  /**
   * Kontaktový filter (migrácia 023b). `skip_contacts = true` znamená „nepíš
   * ľuďom, ktorých má v Telegram kontaktoch" — rodine a známym. Bolo to
   * globálne v env repliky, čo umlčalo kamaráta jedného klienta bez toho, aby
   * o tom ktokoľvek vedel; odteraz je to vec jednej modelky.
   */
  skip_contacts: boolean;
  /** Telegram chat id, ktoré filtrom prejdú aj tak — na testovanie s kamošmi. */
  contact_exceptions: number[];
  /**
   * Migrácia 20260819260000 — `personal` (default) alebo `easy`. Rozhoduje LEN
   * o tom, koľko polí formulár ukáže; worker o tomto stĺpci nevie a personu
   * číta rovnako v oboch módoch.
   */
  setup_mode: string;
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
  /**
   * Migrácia 027 — hranica pre KLIENTOVE prehľady. Klient si ňou dá čísla na
   * nulu a sleduje modelku odznova; `usage_events` sa pritom nemaže a admin
   * pohľady ju ignorujú. `null` = počíta sa od začiatku.
   */
  stats_since: string | null;
  /**
   * Migrácia 20260819150000 — koľko modeliek smie účet mať naraz. Strop drží
   * trigger `models_slot_limit` v DB; toto je len číslo pre UI. Účty s rolou
   * admin/superadmin alebo plánom `vip` sú vyňaté a hodnota im nič nehovorí.
   */
  model_slots: number;
  /**
   * Kto z Telegramu za tento účet platil (migrácia 20260819200000). Vyplní sa
   * pri prvej platbe v Stars a slúži na to, aby ďalšia faktúra mohla prísť
   * rovno do jeho chatu. `null` = ešte cez Telegram neplatil.
   */
  telegram_user_id: number | null;
};

/** Modelka + čísla, ktoré chce klient vidieť na karte. */
export type ModelStats = {
  chats: number;
  converted: number;
  spentToday: number;
};

/** Prihlásený používateľ, inak redirect na login (layout `/app` to už rieši). */
export async function requireUser(): Promise<User> {
  const user = await getUser();
  if (!user) redirect("/login");
  return user;
}

/**
 * Odomknutý účet, inak redirect na `/locked`.
 *
 * `/locked` je ZÁMERNE mimo `/app`: keby bola pod ním, layout `/app` by
 * redirectoval sám do seba (slučka) a zamknutý človek by videl workspace
 * sidebar, ktorý aj tak nesmie použiť.
 *
 * Toto je pohodlie, nie hranica — tou je RLS `models_owner_insert`
 * (migrácia 20260819120000). Ide o to, aby človek dostal vetu namiesto chyby
 * z databázy.
 */
export async function requireUnlocked(): Promise<AccountRow> {
  const account = await getAccount();
  if (!account) redirect("/login");
  if (!isUnlocked(account)) redirect("/locked");
  return account;
}

// React `cache` žije iba v rámci jedného serverového renderu/requestu. Deduplikuje
// layout + stránku bez toho, aby miešal dáta medzi používateľmi.
export const getAccount = cache(async function getAccount(): Promise<AccountRow | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("accounts")
    .select(
      "id, email, credit_balance_usd, created_at, role, plan, stats_since, model_slots, " +
        "telegram_user_id",
    )
    .maybeSingle();

  // Chyba dotazu NIE JE „účet neexistuje". Kým sa sem vracalo len `data`,
  // zabudnutý column grant na novom stĺpci (`stats_since`, migrácia 027) sa
  // tváril ako odhlásený človek: karta Voice hlásila „No ElevenLabs key",
  // hoci kľúč v databáze bol, a v hlavičke svietila nula coinov. Hodinu sa
  // hľadalo v šifrovaní niečo, čo bolo obyčajné „permission denied for
  // column". Nech to nabudúce spadne nahlas a hneď na správnom mieste.
  if (error) {
    throw new Error(`Could not load your account: ${error.message}`);
  }
  return (data as AccountRow | null) ?? null;
});

export const listModels = cache(async function listModels(): Promise<ModelRow[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("models")
    .select(MODEL_COLUMNS)
    .order("created_at", { ascending: true });

  if (error) throw new Error(`Could not load your models: ${error.message}`);
  return (data ?? []) as unknown as ModelRow[];
});

/** Modelka podľa id — RLS zabezpečí, že cudziu nikdy nevráti. */
export const getModel = cache(async function getModel(id: string): Promise<ModelRow | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("models")
    .select(MODEL_COLUMNS)
    .eq("id", id)
    .maybeSingle();
  return (data as unknown as ModelRow | null) ?? null;
});

/** Ako `getModel`, ale cudzie/neexistujúce id je 404 (nie prázdna stránka). */
export async function requireModel(id: string): Promise<ModelRow> {
  const model = await getModel(id);
  if (!model) notFound();
  return model;
}

/**
 * `requireModel` + kontrola, že tá karta k typu agenta vôbec patrí.
 *
 * Tab bar karty, ktoré typ nemá, nevykreslí — ale ručne zadaná URL by ich
 * otvorila a mapa `MODEL_TYPE_TABS` by bola len kozmetika. 404 je správna
 * odpoveď: tá stránka pre túto modelku neexistuje.
 */
export async function requireModelTab(
  id: string,
  slug: ModelTabSlug,
): Promise<ModelRow> {
  const model = await requireModel(id);
  if (!modelTypeHasTab(model.model_type, slug)) notFound();
  await zamknuteKarty(slug);
  return model;
}

/**
 * Karty vo výstavbe (`SUPERADMIN_TABS`) sa cudziemu účtu tvária, že neexistujú.
 *
 * `notFound()` a nie redirect zámerne: klient, ktorý adresu nemá poznať, sa
 * nemá dozvedieť, že tam niečo je a je mu to odopreté. Skrytie v tab bare je
 * len pohodlie — hranica je tu a v API routách.
 */
async function zamknuteKarty(slug: ModelTabSlug): Promise<void> {
  if (!tabIsSuperadminOnly(slug)) return;
  const { getViewerRole } = await import("@/lib/admin");
  if ((await getViewerRole()) !== "superadmin") notFound();
}

/**
 * To isté o poschodie nižšie — podkarta (`/telegram/photos`, `/fanvue/chats`).
 * Kontroluje aj rodiča: karta, ktorú typ nemá, nesmie mať otvorenú podstránku.
 */
export async function requireModelSubTab(
  id: string,
  tab: ModelTabSlug,
  sub: ModelSubTabSlug,
): Promise<ModelRow> {
  const model = await requireModel(id);
  if (!modelTypeHasSubTab(model.model_type, tab, sub)) notFound();
  await zamknuteKarty(tab);
  return model;
}

/* --------------------------------------------------------------------------
   settings.ai_paused — „beží, ale mlčí"
--------------------------------------------------------------------------- */
/**
 * `settings.ai_paused` je globálna pauza odpovedania. Nastavuje ju worker sám
 * pri `PeerFloodError` (`userbot.py`) a Telegram control bot — teda dve miesta
 * MIMO dashboardu. Bez tohto čítania klient pozerá na zelené „Active" a diví
 * sa, prečo modelka nikomu neodpisuje.
 *
 * ZÁMERNE ODDELENÉ OD `models.status`: status hovorí, či agent vôbec beží
 * (power button), `ai_paused` hovorí, či beží a mlčí. Zlúčiť ich by znamenalo,
 * že „Resume replies" po flood warningu reštartne Telethon session — presne to,
 * čo sa po flood warningu robiť nemá.
 *
 * `paused_until` je tretia cesta k tomu istému tichu: uspatie na pár hodín
 * z control bota. Číta sa TU spolu s `ai_paused` — inak by dashboard ukazoval
 * zelené „Active" pri modelke, ktorá spí, teda presne tú chybu, kvôli ktorej
 * toto čítanie vzniklo.
 */
export async function getPausedMap(
  modelIds: string[],
): Promise<Record<string, boolean>> {
  const paused: Record<string, boolean> = {};
  for (const id of modelIds) paused[id] = false;
  if (modelIds.length === 0) return paused;

  const supabase = await createClient();
  const { data } = await supabase
    .from("settings")
    .select("model_id, ai_paused, paused_until")
    .in("model_id", modelIds);

  for (const row of data ?? []) {
    paused[row.model_id as string] =
      Boolean(row.ai_paused) || sleeping(row.paused_until);
  }
  return paused;
}

/** Ako `getPausedMap`, ale pre jednu modelku. Chýbajúci riadok = nie je pauza. */
export const isAiPaused = cache(async function isAiPaused(modelId: string): Promise<boolean> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("settings")
    .select("ai_paused, paused_until")
    .eq("model_id", modelId)
    .maybeSingle();
  return Boolean(data?.ai_paused) || sleeping(data?.paused_until);
});

/**
 * Spí ešte? Nečitateľná značka = nespí.
 *
 * Rovnaké pravidlo ako vo workeri (`db._v_buducnosti`): pri pochybnosti sa
 * NEHLÁSI pauza. Falošné „paused" by klienta poslalo hľadať poruchu, ktorá
 * neexistuje.
 */
function sleeping(value: unknown): boolean {
  if (!value) return false;
  const until = new Date(String(value));
  return !Number.isNaN(until.getTime()) && until.getTime() > Date.now();
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

/* --------------------------------------------------------------------------
   Jej deň
   
   Worker si deň losuje deterministicky (`worker/src/den.py`), ale Pythonom —
   v prehliadači sa to nedá zopakovať. Aby dashboard ukazoval, čo modelka
   NAOZAJ robí, a nie odhad podľa tvaru rozvrhu, worker si svoj plán raz denne
   zapíše do `model_schedule.today_plan` a tu ho len čítame.
-------------------------------------------------------------------------- */

export type DayBlock = {
  od: number; // minúta dňa (môže presiahnuť 1440 — po polnoci)
  do: number;
  kde: string;
  co: string;
  odozva: number;
};

export type DayPlan = {
  tz: string;
  startMin: number;
  endMin: number;
  /** Lokálny dátum modelky, ku ktorému plán patrí — nie dátum servera. */
  date: string | null;
  blocks: DayBlock[];
};

const DEFAULT_TZ = "America/Los_Angeles";

function readBlocks(raw: unknown): DayBlock[] {
  if (!Array.isArray(raw)) return [];
  const out: DayBlock[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const b = item as Record<string, unknown>;
    const od = Number(b.od);
    const koniec = Number(b.do);
    // Blok bez zmysluplného rozsahu by na krivke bol neviditeľný alebo by ju
    // celú rozhodil — radšej ho preskočiť než kresliť nezmysel.
    if (!Number.isFinite(od) || !Number.isFinite(koniec) || koniec <= od) continue;
    out.push({
      od,
      do: koniec,
      kde: typeof b.kde === "string" ? b.kde : "",
      co: typeof b.co === "string" ? b.co : "",
      odozva: Number.isFinite(Number(b.odozva)) ? Number(b.odozva) : 1,
    });
  }
  return out.sort((a, b) => a.od - b.od);
}

/** Minúta dňa z databázy. `null` je „nenastavené", nie polnoc. */
function minuta(raw: unknown, inak: number): number {
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 && value < 1440 ? Math.round(value) : inak;
}

export async function getDayPlans(modelIds: string[]): Promise<Record<string, DayPlan>> {
  const plans: Record<string, DayPlan> = {};
  if (modelIds.length === 0) return plans;

  const supabase = await createClient();
  const [behavior, schedule] = await Promise.all([
    supabase
      .from("behavior")
      .select("model_id, active_tz, active_start_min, active_end_min")
      .in("model_id", modelIds),
    supabase
      .from("model_schedule")
      .select("model_id, today_plan, today_date")
      .in("model_id", modelIds),
  ]);

  const dni = new Map<string, { blocks: DayBlock[]; date: string | null }>();
  for (const row of schedule.data ?? []) {
    dni.set(row.model_id as string, {
      blocks: readBlocks(row.today_plan),
      date: (row.today_date as string | null) ?? null,
    });
  }

  for (const row of behavior.data ?? []) {
    const id = row.model_id as string;
    const den = dni.get(id);
    plans[id] = {
      tz: (row.active_tz as string) || DEFAULT_TZ,
      startMin: minuta(row.active_start_min, 9 * 60),
      endMin: minuta(row.active_end_min, 2 * 60),
      date: den?.date ?? null,
      blocks: den?.blocks ?? [],
    };
  }
  return plans;
}

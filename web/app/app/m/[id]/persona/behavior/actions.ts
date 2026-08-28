"use server";

import { createClient } from "@/lib/supabase/server";
import { isTimeZone } from "@/lib/timezone";

/**
 * Uloženie chovania. Stĺpce presne podľa migrácie 003 (+ 010) — `eleven_key`
 * ani `eleven_key_enc` medzi nimi nie sú a nikdy nebudú: rola `authenticated`
 * na ne nemá grant a od migrácie 017 kľúč ani nesedí na modelke, ale na účte
 * (`app/app/account/actions.ts`).
 *
 * Túto akciu volajú DVE karty — Behavior (štýl, časovanie, limity) a Voice
 * (hlas a všetko okolo neho). Je to tá istá tabuľka a tie isté rozsahy, takže
 * druhý validátor by bol len druhé miesto, kde sa dá zabudnúť.
 *
 * Rozsahy strážime aj tu, nielen v UI: číslo z konzoly nesmie modelke nastaviť
 * odpoveď za 0 sekúnd (a tým ju poslať rovno do Telegram banu).
 */

export type SaveResult = { error?: string };

const ENUMS: Record<string, readonly string[]> = {
  mode: ["real", "ai"],
  // Odkial berie hlas: klientov ElevenLabs kluc, alebo nas katalog.
  voice_source: ["own", "managed"],
  heat: ["mild", "medium", "hot"],
  slang: ["none", "light", "medium"],
  // Kvalita konverzácie. `quality` je predvolené a je to model, na ktorom to
  // beží dnes; `economy` je rádovo lacnejší model pri NEZMENENOM prompte —
  // vie presne to isté, čo má robiť, len to napíše menej vycibrene.
  chat_tier: ["quality", "economy"],
  voice_ambience: [
    "home",
    "bedroom",
    "kitchen",
    "bathroom",
    "car",
    "outside",
    "cafe",
    "gym",
    "none",
  ],
  voice_strength: ["soft", "real", "rough"],
};

const BOOLEANS = [
  "no_diacritics",
  "activity_waves",
  "voices_enabled",
  "morning_enabled",
  "photos_enabled",
  // Výnimky z pravidiel hlasoviek (migrácia 010) — karta Voice.
  "voice_when_asked",
  "voice_when_doubted",
  "voice_when_he_voices",
  "voice_when_away",
  "voice_on_goodnight",
  "voice_when_hot",
] as const;

/** stĺpec → [min, max] pre celé čísla. */
const INTEGERS: Record<string, [number, number]> = {
  active_start_min: [0, 1439],
  active_end_min: [0, 1439],
  debounce_min_s: [0, 600],
  debounce_max_s: [0, 600],
  read_delay_min_s: [0, 3600],
  read_delay_max_s: [0, 3600],
  reply_delay_min_s: [0, 3600],
  reply_delay_max_s: [0, 3600],
  quick_read_max_s: [0, 600],
  quick_reply_min_s: [0, 600],
  quick_reply_max_s: [0, 600],
  seen_only_min_s: [0, 86_400],
  seen_only_max_s: [0, 86_400],
  long_pause_min_s: [0, 86_400],
  long_pause_max_s: [0, 86_400],
  defer_min_s: [0, 172_800],
  defer_max_s: [0, 172_800],
  greeting_gap_hours: [0, 168],
  summary_every: [1, 200],
  max_replies_per_hour: [1, 500],
  max_links_per_hour: [0, 50],
  photo_cooldown_min: [0, 1440],
  morning_max_per_day: [0, 500],
  // Tri stropy, ktoré držia účet mimo dohľadu Telegramu (`behavior.SAFETY_FIELDS`
  // vo workeri). Worker ich číta od začiatku — `userbot._aktivne_rozhovory`,
  // `_smie_oslovit` — len sa doteraz nedali nastaviť inak než kontrolným botom.
  // Nula je vo workeri „strop vypnutý“ (`limity.smie_oslovit`, `limity.ma_miesto`),
  // preto rozsah začína na nule; `chat_slot_min` nie, tam by nula ticho vypla
  // aj `max_active_chats`.
  max_outreach_per_hour: [0, 200],
  // Dĺžka okna konverzácie v dňoch (Telegram → Settings). Nula tu nedáva
  // zmysel a databáza ju aj tak odmietne (`behavior_chat_days_check`).
  chat_days: [1, 14],
  max_active_chats: [0, 100],
  chat_slot_min: [1, 1440],
};

/** Pravdepodobnosti 0–1. */
const FRACTIONS = [
  "quick_reply_chance",
  "seen_only_chance",
  "long_pause_chance",
  "defer_reply_chance",
  "question_chance",
  "gag_chance",
  "voice_chance",
  "voice_ambience_level",
] as const;

/**
 * Desatinné hodnoty s vlastnými medzami.
 *
 * Rozsahy hlasovky (029) sú tu, nie medzi `FRACTIONS`: sekundy nie sú
 * pravdepodobnosti a hlasitosť má strop nižšie než 1. Medze sú tie isté, aké
 * stráži `behavior_voice_ranges_check` v databáze — tá je skutočná obrana,
 * toto je len zrozumiteľnejšia chyba.
 */
const DECIMALS: Record<string, [number, number]> = {
  voice_tempo: [0.5, 2],
  voice_volume_min: [0.01, 0.6],
  voice_volume_max: [0.01, 0.6],
  voice_lead_min: [0, 6],
  voice_lead_max: [0, 6],
  voice_tail_min: [0, 8],
  voice_tail_max: [0, 8],
};

export async function saveBehaviorAction(
  modelId: string,
  patch: Record<string, unknown>,
): Promise<SaveResult> {
  const update: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(patch)) {
    if (key in ENUMS) {
      if (typeof value !== "string" || !ENUMS[key].includes(value)) {
        return { error: `Unexpected value for ${key}.` };
      }
      update[key] = value;
      continue;
    }
    if ((BOOLEANS as readonly string[]).includes(key)) {
      update[key] = Boolean(value);
      continue;
    }
    if (key in INTEGERS) {
      const number = Number(value);
      if (!Number.isFinite(number)) return { error: `${key} must be a number.` };
      const [min, max] = INTEGERS[key];
      update[key] = clamp(Math.round(number), min, max);
      continue;
    }
    if ((FRACTIONS as readonly string[]).includes(key)) {
      const number = Number(value);
      if (!Number.isFinite(number)) return { error: `${key} must be a number.` };
      update[key] = clamp(number, 0, 1);
      continue;
    }
    if (key in DECIMALS) {
      const number = Number(value);
      if (!Number.isFinite(number)) return { error: `${key} must be a number.` };
      const [min, max] = DECIMALS[key];
      update[key] = clamp(number, min, max);
      continue;
    }
    if (key === "eleven_voice_id") {
      // Id hlasu z ElevenLabs — 20 znakov base62. Nevalidujeme, či ten hlas na
      // účte naozaj je (to by znamenalo volať ElevenLabs pri každom uložení);
      // strážime len tvar, aby sa do stĺpca nedostal odpad z konzoly. Prázdne
      // je legitímne: „žiadny vlastný hlas".
      const voice = String(value ?? "").trim();
      if (voice && !/^[A-Za-z0-9]{16,40}$/.test(voice)) {
        return { error: "That is not an ElevenLabs voice id." };
      }
      update.eleven_voice_id = voice;
      continue;
    }
    if (key === "managed_voice_id") {
      // uuid z `managed_voices`, alebo prazdne (= ziadny nas hlas vybraty).
      const raw = String(value ?? "").trim();
      if (raw && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)) {
        return { error: "That is not a voice we offer." };
      }
      update.managed_voice_id = raw || null;
      continue;
    }
    if (key === "active_tz") {
      if (typeof value !== "string" || !isTimeZone(value)) {
        return { error: "That time zone is not one Telegram servers would recognise." };
      }
      update.active_tz = value;
      continue;
    }
    return { error: `Unknown field: ${key}` };
  }

  if (Object.keys(update).length === 0) return {};
  update.updated_at = new Date().toISOString();

  const supabase = await createClient();
  const { error } = await supabase.from("behavior").update(update).eq("model_id", modelId);

  if (error) return { error: error.message };
  return {};
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

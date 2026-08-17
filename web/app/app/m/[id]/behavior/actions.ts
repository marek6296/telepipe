"use server";

import { createClient } from "@/lib/supabase/server";

/**
 * Uloženie chovania. Stĺpce presne podľa migrácie 003 — `eleven_key` medzi nimi
 * chýba zámerne: rola `authenticated` naň nemá grant (fáza 3 ho bude plniť
 * server-side), takže by zápis aj tak skončil chybou.
 *
 * Rozsahy strážime aj tu, nielen v UI: číslo z konzoly nesmie modelke nastaviť
 * odpoveď za 0 sekúnd (a tým ju poslať rovno do Telegram banu).
 */

export type SaveResult = { error?: string };

const ENUMS: Record<string, readonly string[]> = {
  mode: ["real", "ai"],
  heat: ["mild", "medium", "hot"],
  slang: ["none", "light", "medium"],
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

/** Tempo reči — mimo 0.5–2.0 znie hlasovka ako porucha. */
const DECIMALS: Record<string, [number, number]> = {
  voice_tempo: [0.5, 2],
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

/** Overenie cez Intl — zoznam zón na serveri je zdroj pravdy, nie náš select. */
function isTimeZone(value: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value });
    return true;
  } catch {
    return false;
  }
}

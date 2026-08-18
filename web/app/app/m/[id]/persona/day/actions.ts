"use server";

import { revalidatePath } from "next/cache";

import { OUT_OF_CREDITS_MSG, creditState, hasCredit, recordUsage } from "@/lib/credits";
import { chatJson, llmConfigured, llmModel, parseJsonish, type ChatMessage } from "@/lib/llm";
import { getModel } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import {
  MAX_ACTIVITIES,
  MAX_PACE,
  MAX_TEXT,
  MIN_PACE,
  PLACES,
  normaliseActivities,
} from "@/lib/schedule";
import {
  SCHEDULE_SYSTEM_PROMPT,
  buildScheduleUserMessage,
  mapScheduleDraft,
  type ScheduleDraft,
} from "@/lib/schedule-draft";

/**
 * Uloženie denného rozvrhu (migrácia 022). Worker ho číta priebežne, takže
 * zmena platí do piatich minút — žiadny reštart, žiadne „Save" tlačidlo.
 *
 * Validujeme aj tu, hoci to isté stráži CHECK v databáze. Dôvod je hláška:
 * z „new row violates check constraint model_schedule_activities" sa klient
 * nedozvie nič. Tvrdou hranicou ostáva DB — toto je preklad do ľudskej reči.
 */

export type SaveResult = { error?: string };

const INTEGERS: Record<string, [number, number]> = {
  wake_weekday_start_min: [0, 1439],
  wake_weekday_end_min: [0, 1439],
  wake_weekend_start_min: [0, 1439],
  wake_weekend_end_min: [0, 1439],
};

export async function saveScheduleAction(
  modelId: string,
  patch: Record<string, unknown>,
): Promise<SaveResult> {
  const update: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(patch)) {
    if (key in INTEGERS) {
      const number = Number(value);
      if (!Number.isFinite(number)) return { error: `${key} must be a time.` };
      const [min, max] = INTEGERS[key];
      update[key] = Math.min(max, Math.max(min, Math.round(number)));
      continue;
    }
    if (key === "night_place") {
      if (typeof value !== "string" || !(PLACES as readonly string[]).includes(value)) {
        return { error: "That is not one of her rooms." };
      }
      update.night_place = value;
      continue;
    }
    if (key === "night_what" || key === "night_arrival") {
      const text = String(value ?? "").trim().slice(0, MAX_TEXT);
      if (key === "night_what" && !text) {
        return { error: "Say what she is doing at night — she leans on it in every reply." };
      }
      update[key] = text;
      continue;
    }
    if (key === "night_pace") {
      const number = Number(value);
      if (!Number.isFinite(number)) return { error: "night_pace must be a number." };
      update.night_pace = Math.min(MAX_PACE, Math.max(MIN_PACE, number));
      continue;
    }
    if (key === "activities") {
      const items = normaliseActivities(value);
      if (items.length === 0) {
        return {
          error:
            "Her day needs at least one thing in it — otherwise she is in bed from morning to night.",
        };
      }
      if (items.length > MAX_ACTIVITIES) {
        return { error: `A day can hold at most ${MAX_ACTIVITIES} entries.` };
      }
      update.activities = items;
      continue;
    }
    return { error: `Unknown field: ${key}` };
  }

  if (Object.keys(update).length === 0) return {};

  // Prehodené okno („from 13:00 to 11:00") by DB odmietla CHECK-om. Klient to
  // myslel ako rozsah, tak ho narovnáme, nech nedostane chybu za preklep.
  swap(update, "wake_weekday_start_min", "wake_weekday_end_min");
  swap(update, "wake_weekend_start_min", "wake_weekend_end_min");

  update.updated_at = new Date().toISOString();

  const supabase = await createClient();
  const { error } = await supabase
    .from("model_schedule")
    .update(update)
    .eq("model_id", modelId);

  if (error) return { error: error.message };
  return {};
}

/**
 * Návrat k pôvodnému dňu. Defaulty sú v schéme (migrácia 022), preto to musí
 * spraviť databáza — inak by ten istý deň bol napísaný na dvoch miestach.
 */
export async function resetScheduleAction(modelId: string): Promise<SaveResult> {
  const supabase = await createClient();
  const { error } = await supabase.rpc("reset_model_schedule", { p_model: modelId });
  if (error) return { error: error.message };
  revalidatePath(`/app/m/${modelId}/persona/day`);
  return {};
}

/** Obe hranice v patchi a prehodené? Narovnaj ich. */
function swap(update: Record<string, unknown>, from: string, to: string): void {
  const a = update[from];
  const b = update[to];
  if (typeof a === "number" && typeof b === "number" && a > b) {
    update[from] = b;
    update[to] = a;
  }
}

/* --------------------------------------------------------------------------
   „Opíš jej deň vlastnými slovami"
--------------------------------------------------------------------------- */

export type GenerateScheduleResult = {
  error?: string;
  draft?: ScheduleDraft;
  /** Čo sme opravili sami (rozšírený rozsah, dorovnaná rýchlosť…). */
  warnings?: string[];
};

/** Koľkokrát smie model dostať šancu odovzdať použiteľný rozvrh. */
const TRIES = 2;
/** Kratší popis než toto nie je deň, ale nadpis. */
const MIN_DESCRIPTION = 20;
const MAX_DESCRIPTION = 4000;

/**
 * Popis vlastnými slovami → hotový rozvrh. NIČ NEZAPISUJE.
 *
 * Rovnaká cesta ako asistovaná persona (`persona/build/actions.ts`): klient
 * najprv uvidí ukážku dňa, ktorý mu vznikol, a až „Apply" ho uloží — cez
 * `saveScheduleAction`, teda cez ten istý whitelist ako ručný editor.
 *
 * Každé volanie modelu (aj to, ktoré vrátilo nepoužiteľný JSON) ide do
 * `usage_events`: tokeny už zhoreli, nech ich neplatíme my.
 */
export async function generateScheduleDraftAction(
  modelId: string,
  rawDescription: unknown,
): Promise<GenerateScheduleResult> {
  // RLS: cudzie id sa sem nedostane, `getModel` vráti null.
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  const description = String(rawDescription ?? "").trim().slice(0, MAX_DESCRIPTION);
  if (description.length < MIN_DESCRIPTION) {
    return {
      error:
        "Tell us a bit more about her day — a couple of sentences about when she gets up and what she does.",
    };
  }

  if (!llmConfigured()) {
    return { error: "The AI helper is not switched on for this deployment." };
  }

  // Zostatok sa kontroluje PRED volaním — inak by účet bez kreditu vygeneroval
  // deň a dozvedel sa o tom až z faktúry.
  const credit = await creditState();
  if (!hasCredit(credit)) return { error: OUT_OF_CREDITS_MSG };

  const supabase = await createClient();
  const { data: persona } = await supabase
    .from("persona")
    .select("city")
    .eq("model_id", model.id)
    .maybeSingle();

  const messages: ChatMessage[] = [
    { role: "system", content: SCHEDULE_SYSTEM_PROMPT },
    {
      role: "user",
      content: buildScheduleUserMessage(description, String(persona?.city ?? "")),
    },
  ];

  let lastProblem = "";

  for (let attempt = 1; attempt <= TRIES; attempt++) {
    const result = await chatJson(messages, { maxTokens: 6000, temperature: 0.8 });

    // Účtujeme vždy, aj pri páde: poskytovateľ si tokeny z každého pokusu berie.
    await recordUsage(model.id, "chat", llmModel(), result.usage);

    if (!result.ok) return { error: result.error ?? "The AI helper did not answer." };

    const parsed = parseJsonish(result.content);
    if (parsed === undefined) {
      lastProblem = "The answer was not valid JSON.";
    } else {
      const mapped = mapScheduleDraft(parsed);
      if (mapped.draft) return { draft: mapped.draft, warnings: mapped.warnings };
      lastProblem = mapped.errors.join(" ");
    }

    if (attempt === TRIES) break;

    // Druhý pokus dostane vlastnú chybu späť — bez nej by model zopakoval to
    // isté a klient by zaplatil dve rovnaké odpovede.
    messages.push({ role: "assistant", content: result.content.slice(0, 12000) });
    messages.push({
      role: "user",
      content:
        `That schedule was rejected: ${lastProblem}\n` +
        "Send the whole JSON object again, corrected. Same keys, nothing else, raw JSON only.",
    });
  }

  return {
    error:
      "The AI helper could not put together a day that holds together. Try describing her week in a bit more detail, or build it yourself below.",
  };
}

/**
 * Zápis vygenerovaného dňa. Draft prichádza z prehliadača, takže ide tou istou
 * cestou ako ručná úprava — `saveScheduleAction` má whitelist aj rozsahy a
 * databáza má CHECK. UI nie je hranica.
 */
export async function applyScheduleDraftAction(
  modelId: string,
  rawDraft: unknown,
): Promise<SaveResult> {
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };
  if (!rawDraft || typeof rawDraft !== "object") {
    return { error: "There is nothing to apply." };
  }
  const draft = rawDraft as Record<string, unknown>;

  const saved = await saveScheduleAction(model.id, {
    wake_weekday_start_min: draft.wake_weekday_start_min,
    wake_weekday_end_min: draft.wake_weekday_end_min,
    wake_weekend_start_min: draft.wake_weekend_start_min,
    wake_weekend_end_min: draft.wake_weekend_end_min,
    night_place: draft.night_place,
    night_what: draft.night_what,
    night_pace: draft.night_pace,
    night_arrival: draft.night_arrival,
    activities: draft.activities,
  });
  if (saved.error) return saved;

  revalidatePath(`/app/m/${modelId}/persona/day`);
  return {};
}

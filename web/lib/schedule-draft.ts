/**
 * „Opíš jej deň vlastnými slovami" → náš rozvrh.
 *
 * Rovnaká stavba ako `persona-draft.ts` a zámerne: prompt, ktorý modelu opisuje
 * NAŠE hranice, a mapper, ktorý jeho odpoveď na tie hranice naozaj zúži. Keby
 * boli inde, prvá zmena rozsahu by rozišla popis od kontroly.
 *
 * MODEL NEPOZNÁ NAŠE STĹPCE. Vracia ľudské kľúče (`room`, `doing`,
 * `reply_speed`, `days` ako „mon"/„tue"), preklad na `place`/`what`/`pace`/
 * `days: [0..6]` robí výhradne mapper nižšie. Model tak nemá ako trafiť stĺpec,
 * o ktorom sme mu nepovedali.
 *
 * ČO SA NEDÁ NECHAŤ NA MODEL
 * --------------------------
 * `den.py` má tri vyladené vlastnosti, ktoré rozhodujú o tom, či deň pôsobí ako
 * život alebo ako rozvrh z papiera — a model ich poruší, ak sa to nekontroluje:
 *
 *   1. trvania sú ROZSAHY, nie pevné časy (fitko 14:00–15:30 je papier,
 *      človek príde 14:03);
 *   2. rozsah musí byť dosť široký, aby hranica nevyšla okrúhlo;
 *   3. každý deň v týždni má vlastný priebeh, nie variáciu jedného — inak je
 *      po týždni vzor vidieť.
 *
 * Preto sa po generovaní kontroluje tvar každého dňa a zhoda medzi dňami; keď
 * nesedí, ide to modelu späť ako chyba, nie do databázy.
 *
 * VÝSTUP JE PO ANGLICKY. Klient smie písať v akomkoľvek jazyku; uložené vety
 * sú anglické, rovnako ako persona (`tone`, `msg_style`, ...), lebo sa vlepujú
 * do toho istého promptu. Simonine pôvodné slovenské vety ostávajú, aké boli —
 * generuje sa len to, čo si klient vypýta nanovo.
 *
 * Súbor nesmie importovať nič serverové: beží aj v `scripts/schedule-draft-test.mts`.
 */

import {
  ALL_DAYS,
  MAX_ACTIVITIES,
  MAX_DURATION,
  MAX_PACE,
  MAX_TEXT,
  MIN_DURATION,
  MIN_PACE,
  PACE_OPTIONS,
  PLACES,
  PLACE_LABEL,
  WEEKDAYS,
  nearestPace,
  type Place,
  type ScheduleActivity,
} from "./schedule.ts";

/* --------------------------------------------------------------------------
   Tvar draftu
-------------------------------------------------------------------------- */

export type ScheduleDraft = {
  wake_weekday_start_min: number;
  wake_weekday_end_min: number;
  wake_weekend_start_min: number;
  wake_weekend_end_min: number;
  night_place: Place;
  night_what: string;
  night_pace: number;
  night_arrival: string;
  activities: ScheduleActivity[];
};

export type ScheduleMapResult = {
  draft?: ScheduleDraft;
  /** Fatálne — s týmto sa deň nedá zložiť, volajúci skúsi ešte raz. */
  errors: string[];
  /** Opravené za pochodu (rozšírený rozsah, dorovnaná rýchlosť). */
  warnings: string[];
};

/* --------------------------------------------------------------------------
   Hranice — musia sedieť s CHECK-om v migrácii 022 a s `den.py`
-------------------------------------------------------------------------- */

/** Najmenej toľko činností musí mať deň, inak to nie je život, ale jeden blok. */
const MIN_PER_DAY = 2;
/** Najužší rozsah trvania, ktorý ešte losuje niečo iné než okrúhle číslo. */
const MIN_SPAN = 10;
/** Najužšie okno vstávania — pod tým je to budík, nie človek. */
const MIN_WAKE_SPAN = 10;

const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

/* --------------------------------------------------------------------------
   Prompt
-------------------------------------------------------------------------- */

const PLACE_LINES = PLACES.map((place) => `  "${place}" — ${PLACE_LABEL[place]}`).join("\n");
const PACE_LINES = PACE_OPTIONS.map(
  (option) => `  ${option.value} — ${option.label.toLowerCase()}`,
).join("\n");

/**
 * Systémový prompt. Opisuje NAŠE hranice, nie „vymysli jej deň" — model má
 * vyplniť formulár, ktorý existuje, a nič mimo neho.
 *
 * Tri pravidlá o rozsahoch a rôznych dňoch sú tu napísané aj napriek tomu, že
 * ich mapper stráži: model, ktorý ich pozná, ich väčšinou dodrží na prvýkrát a
 * klient nezaplatí druhé volanie.
 */
export const SCHEDULE_SYSTEM_PROMPT = `You turn a description of a person's daily life into the exact schedule our system stores for an AI companion agent.

THE DESCRIPTION MAY ARRIVE IN ANY LANGUAGE. Understand it whatever language it is in, but write EVERY output text in natural English.

WHY THIS MATTERS
The schedule decides three things about her, all day long: what she says she is doing when a fan asks, how fast she replies from there, and what her voice notes sound like in the background. A schedule that reads like a printed timetable makes her read like a bot.

OUTPUT
Return ONE JSON object and nothing else. Exactly these keys, no others:

"wake_weekday" — object {"from": "HH:MM", "to": "HH:MM"}. The window she gets up in on Monday to Friday. A window, never a single time.
"wake_weekend" — object {"from": "HH:MM", "to": "HH:MM"}. The same for Saturday and Sunday, usually later.

"activities" — array of 10 to ${MAX_ACTIVITIES} objects, in the order her day runs. Each object:
  "room" — one of these exact values, chosen for how the place SOUNDS behind a voice note:
${PLACE_LINES}
  "doing" — one short line, English, present tense, third person, describing what she is doing there, e.g. "she is at the gym, checking her phone between sets". Under ${MAX_TEXT} characters. This is pasted into her prompt, so keep it factual and ordinary.
  "reply_speed" — one of these exact numbers, how fast she answers from that place:
${PACE_LINES}
  "minutes_min" and "minutes_max" — how long it usually lasts, in minutes, between ${MIN_DURATION} and ${MAX_DURATION}. These MUST be a real range at least ${MIN_SPAN} minutes wide. Never the same number twice, never a fixed clock time.
  "on_arrival" — one short line she says when she has just got there, English, e.g. "just got out of the gym". Use "" when arriving is not worth mentioning.
  "days" — array of day names from "mon", "tue", "wed", "thu", "fri", "sat", "sun". Which days this happens on.

"night" — object {"room", "doing", "reply_speed", "on_arrival"} for the last stretch of her day in bed. It has no duration: it runs until she falls asleep.

THE THREE RULES THAT MAKE IT BELIEVABLE
1. Durations are RANGES, never fixed. A person does not leave the gym at exactly 15:30 every time.
2. Every one of the seven weekdays must have a DIFFERENT shape — a different sequence of rooms, not the same day with the times moved. Give her different anchors on different days: training days, shoot days, a day of errands, a night out, a lazy day.
3. Every weekday needs at least ${MIN_PER_DAY} activities and her day must be full from when she wakes until late evening. If the description does not say what she does on some day, invent something ordinary and consistent with the rest — an empty day is worse than a plausible invention.

RULES
- Never invent a room name or a reply speed that is not in the lists above.
- Never write clock times inside "doing" or "on_arrival" — the times come from the ranges.
- Keep every text in the third person about her, plain and short. No markdown, no emoji, no bullet points.
- She is always an adult and the schedule is always ordinary daily life.
- Output raw JSON. No markdown fence, no commentary, no trailing text.`;

/** Popis od klienta → user message. Bez našich stĺpcov, bez našich mien polí. */
export function buildScheduleUserMessage(description: string, city = ""): string {
  const lines = ["Build her daily schedule from this description."];
  if (city.trim()) lines.push(`She lives in ${city.trim()}.`);
  lines.push("", "The operator's own words:", description.trim());
  return lines.join("\n");
}

/* --------------------------------------------------------------------------
   Odpoveď modelu → náš rozvrh
-------------------------------------------------------------------------- */

/**
 * JSON od modelu → draft rozvrhu. Nič nezapisuje.
 *
 * `errors` sú dôvod na druhý pokus (a posielajú sa modelu späť), `warnings`
 * len hovoria, čo sme opravili sami.
 */
export function mapScheduleDraft(raw: unknown): ScheduleMapResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return { errors: ["The answer was not a JSON object."], warnings };
  }
  const input = raw as Record<string, unknown>;

  for (const key of Object.keys(input)) {
    if (!["wake_weekday", "wake_weekend", "activities", "night"].includes(key)) {
      warnings.push(`Ignored an unexpected key: ${key}.`);
    }
  }

  const weekday = readWindow(input.wake_weekday, "wake_weekday", errors, warnings);
  const weekend = readWindow(input.wake_weekend, "wake_weekend", errors, warnings);
  const night = readNight(input.night, errors, warnings);

  const activities: ScheduleActivity[] = [];
  let fixedDurations = 0;

  if (!Array.isArray(input.activities)) {
    errors.push(`"activities" must be an array.`);
  } else if (input.activities.length === 0) {
    errors.push(`"activities" is empty — her day would have nothing in it.`);
  } else {
    if (input.activities.length > MAX_ACTIVITIES) {
      warnings.push(`Only the first ${MAX_ACTIVITIES} activities were kept.`);
    }
    input.activities.slice(0, MAX_ACTIVITIES).forEach((item, index) => {
      const mapped = readActivity(item, index, errors, warnings);
      if (!mapped) return;
      if (mapped.wasFixed) fixedDurations += 1;
      activities.push(mapped.activity);
    });
  }

  if (activities.length > 0) {
    // Pravidlo 1: trvania sú rozsahy. Jedno pevné je preklep a opravíme ho;
    // polovica pevných znamená, že model pravidlo prehliadol a má to spraviť
    // znova — inak by mala každý deň rovnako dlhé fitko na minútu.
    if (fixedDurations * 2 > activities.length) {
      errors.push(
        `${fixedDurations} of ${activities.length} activities had no real duration range. ` +
          `"minutes_min" and "minutes_max" must differ by at least ${MIN_SPAN} minutes.`,
      );
    }
    checkDays(activities, errors, warnings);
  }

  if (errors.length > 0) return { errors, warnings };

  return {
    errors,
    warnings,
    draft: {
      wake_weekday_start_min: weekday![0],
      wake_weekday_end_min: weekday![1],
      wake_weekend_start_min: weekend![0],
      wake_weekend_end_min: weekend![1],
      night_place: night!.place,
      night_what: night!.what,
      night_pace: night!.pace,
      night_arrival: night!.arrival,
      activities,
    },
  };
}

/**
 * Pravidlá 2 a 3: každý deň musí byť obsadený a žiadne dva dni nesmú mať ten
 * istý priebeh. Toto sa opraviť nedá — obsah vie doplniť len model, takže to
 * ide späť ako chyba s presným menom dňa.
 */
function checkDays(
  activities: ScheduleActivity[],
  errors: string[],
  warnings: string[],
): void {
  const shapes = new Map<string, number[]>();
  const thin: string[] = [];

  for (const day of ALL_DAYS) {
    const mine = activities.filter((activity) => activity.days.includes(day));
    if (mine.length < MIN_PER_DAY) {
      thin.push(WEEKDAYS[day].label);
      continue;
    }
    const shape = mine.map((activity) => activity.place).join(">");
    const seen = shapes.get(shape) ?? [];
    seen.push(day);
    shapes.set(shape, seen);
  }

  if (thin.length > 0) {
    errors.push(
      `${thin.join(", ")} ${thin.length === 1 ? "has" : "have"} fewer than ${MIN_PER_DAY} ` +
        "activities — every weekday needs a full day.",
    );
  }

  const collisions = [...shapes.values()].filter((days) => days.length > 1);
  for (const days of collisions) {
    errors.push(
      `${days.map((day) => WEEKDAYS[day].label).join(" and ")} run through exactly the ` +
        "same places in the same order — every weekday must have its own shape.",
    );
  }

  // Nie chyba, len upozornenie: čo sa do okna nezmestí, sa proste nestane.
  for (const day of ALL_DAYS) {
    const mine = activities.filter((activity) => activity.days.includes(day));
    const shortest = mine.reduce((total, activity) => total + activity.min_minutes, 0);
    if (shortest > 14 * 60) {
      warnings.push(
        `${WEEKDAYS[day].label} is packed so tight that the last entries may never happen.`,
      );
    }
  }
}

/* --------------------------------------------------------------------------
   Kúsky
-------------------------------------------------------------------------- */

function readWindow(
  raw: unknown,
  key: string,
  errors: string[],
  warnings: string[],
): [number, number] | undefined {
  if (!raw || typeof raw !== "object") {
    errors.push(`"${key}" must be an object with "from" and "to" times.`);
    return undefined;
  }
  const item = raw as Record<string, unknown>;
  let from = readClock(item.from);
  let to = readClock(item.to);
  if (from === null || to === null) {
    errors.push(`"${key}" needs "from" and "to" as "HH:MM" times.`);
    return undefined;
  }
  if (to < from) {
    [from, to] = [to, from];
    warnings.push(`${key} came back back-to-front — swapped the two times.`);
  }
  if (to - from < MIN_WAKE_SPAN) {
    to = Math.min(1439, from + 30);
    warnings.push(
      `${key} was a single moment rather than a window — widened it to ${MIN_WAKE_SPAN}+ minutes.`,
    );
  }
  return [from, to];
}

function readNight(
  raw: unknown,
  errors: string[],
  warnings: string[],
): { place: Place; what: string; pace: number; arrival: string } | undefined {
  if (!raw || typeof raw !== "object") {
    errors.push(`"night" must be an object.`);
    return undefined;
  }
  const item = raw as Record<string, unknown>;
  const place = readPlace(item.room);
  if (!place) {
    errors.push(`"night".room is not one of the rooms we know (${JSON.stringify(item.room)}).`);
    return undefined;
  }
  const what = text(item.doing);
  if (!what) {
    errors.push(`"night".doing is empty — she needs something to say about her night.`);
    return undefined;
  }
  return {
    place,
    what,
    pace: readPace(item.reply_speed, "night", errors, warnings) ?? 1,
    arrival: text(item.on_arrival),
  };
}

function readActivity(
  raw: unknown,
  index: number,
  errors: string[],
  warnings: string[],
): { activity: ScheduleActivity; wasFixed: boolean } | undefined {
  const where = `activity ${index + 1}`;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    errors.push(`${where} is not an object.`);
    return undefined;
  }
  const item = raw as Record<string, unknown>;

  const place = readPlace(item.room);
  if (!place) {
    errors.push(`${where} has room ${JSON.stringify(item.room)}, which is not one we know.`);
    return undefined;
  }

  const what = text(item.doing);
  if (!what) {
    errors.push(`${where} has no "doing" line.`);
    return undefined;
  }

  const pace = readPace(item.reply_speed, where, errors, warnings);
  if (pace === undefined) return undefined;

  const days = readDays(item.days);
  if (days.length === 0) {
    errors.push(`${where} is not on any day — "days" must name at least one.`);
    return undefined;
  }

  let low = readMinutes(item.minutes_min);
  let high = readMinutes(item.minutes_max);
  if (low === null || high === null) {
    errors.push(
      `${where} needs "minutes_min" and "minutes_max" between ${MIN_DURATION} and ${MAX_DURATION}.`,
    );
    return undefined;
  }
  if (high < low) {
    [low, high] = [high, low];
    warnings.push(`${where} had its minutes back-to-front — swapped them.`);
  }

  // Pevné trvanie je vyladené pravidlo z `den.py`, nie kozmetika: keby fitko
  // trvalo vždy presne 90 minút, hranice by vychádzali okrúhlo a rozvrh by bolo
  // po pár dňoch vidieť.
  let wasFixed = false;
  if (high - low < MIN_SPAN) {
    wasFixed = true;
    high = Math.min(MAX_DURATION, low + Math.max(MIN_SPAN, Math.round(low * 0.3)));
    warnings.push(`${where} had a fixed length — widened it to ${low}–${high} minutes.`);
  }

  return {
    wasFixed,
    activity: {
      place,
      what,
      pace,
      min_minutes: low,
      max_minutes: high,
      arrival: text(item.on_arrival),
      days,
    },
  };
}

function readPlace(raw: unknown): Place | undefined {
  const value = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  return (PLACES as readonly string[]).includes(value) ? (value as Place) : undefined;
}

function readPace(
  raw: unknown,
  where: string,
  errors: string[],
  warnings: string[],
): number | undefined {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < MIN_PACE || value > MAX_PACE) {
    errors.push(
      `${where} has reply_speed ${JSON.stringify(raw)}, which is not one of the speeds we offer.`,
    );
    return undefined;
  }
  const snapped = nearestPace(value);
  if (snapped !== value) {
    warnings.push(`${where} asked for reply speed ${value} — used the nearest one, ${snapped}.`);
  }
  return snapped;
}

function readMinutes(raw: unknown): number | null {
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  const rounded = Math.round(value);
  if (rounded < MIN_DURATION || rounded > MAX_DURATION) return null;
  return rounded;
}

/** „mon"/„Monday"/0 → 0. Neznáme sa ticho zahodí, prázdny výsledok je chyba. */
function readDays(raw: unknown): number[] {
  if (!Array.isArray(raw)) return [];
  const out = new Set<number>();
  for (const item of raw) {
    if (typeof item === "number" && Number.isInteger(item) && item >= 0 && item <= 6) {
      out.add(item);
      continue;
    }
    if (typeof item !== "string") continue;
    const value = item.trim().toLowerCase().slice(0, 3);
    const index = DAY_KEYS.indexOf(value as (typeof DAY_KEYS)[number]);
    if (index >= 0) out.add(index);
  }
  return ALL_DAYS.filter((day) => out.has(day));
}

function readClock(raw: unknown): number | null {
  if (typeof raw === "number" && Number.isFinite(raw)) {
    const minutes = Math.round(raw);
    return minutes >= 0 && minutes <= 1439 ? minutes : null;
  }
  if (typeof raw !== "string") return null;
  const match = /^(\d{1,2}):(\d{2})$/.exec(raw.trim());
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

function text(raw: unknown): string {
  return typeof raw === "string"
    ? raw.replace(/\s+/g, " ").trim().slice(0, MAX_TEXT)
    : "";
}

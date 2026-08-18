/**
 * Denný život modelky — tvar, popisky a ukážka dňa.
 *
 * Toto je jediné miesto, kde web vie, ako rozvrh vyzerá: server action ho
 * z toho validuje, editor z toho kreslí a ukážka z toho počíta. Zdroj pravdy je
 * `worker/src/den.py` (a migrácia 022) — tu je jeho dvojča pre prehliadač.
 *
 * Súbor je client-safe: žiadny server import, žiadne ikony.
 */

/** Miestnosti, ktoré vie hlasovka ozvučiť. Kľúče = `eleven.AMBIENCES`. */
export const PLACES = [
  "home",
  "bedroom",
  "kitchen",
  "bathroom",
  "car",
  "outside",
  "cafe",
  "gym",
  "none",
] as const;

export type Place = (typeof PLACES)[number];

/**
 * Popisky miest. Klient nemá vedieť, že „none" je kľúč — má vedieť, že to
 * znamená ticho v pozadí hlasovky.
 */
export const PLACE_LABEL: Record<Place, string> = {
  home: "At home",
  bedroom: "Bedroom",
  kitchen: "Kitchen",
  bathroom: "Bathroom",
  car: "In the car",
  outside: "Out and about",
  cafe: "Café",
  gym: "Gym",
  none: "No background sound",
};

/**
 * Ako rýchlo odtiaľ odpisuje. Číslo je násobič oneskorenia, ktorý worker
 * použije na jej bežné časy odpovede z karty Behavior — klient si vyberá
 * vetu, nie koeficient.
 */
export const PACE_OPTIONS = [
  { value: 0.5, label: "Right there — replies in seconds" },
  { value: 0.8, label: "Relaxed — replies quickly" },
  { value: 1, label: "Normal" },
  { value: 1.5, label: "Half-distracted — takes a while" },
  { value: 2.4, label: "Busy — replies between other things" },
  { value: 4, label: "Phone away — barely replies at all" },
] as const;

/** Najbližšia ponúkaná rýchlosť k uloženej hodnote (staré/ručné čísla). */
export function nearestPace(value: number): number {
  let best = PACE_OPTIONS[0].value as number;
  for (const option of PACE_OPTIONS) {
    if (Math.abs(option.value - value) < Math.abs(best - value)) best = option.value;
  }
  return best;
}

/** Pondelok = 0, rovnako ako `date.weekday()` v Pythone. */
export const WEEKDAYS = [
  { value: 0, short: "Mon", label: "Monday" },
  { value: 1, short: "Tue", label: "Tuesday" },
  { value: 2, short: "Wed", label: "Wednesday" },
  { value: 3, short: "Thu", label: "Thursday" },
  { value: 4, short: "Fri", label: "Friday" },
  { value: 5, short: "Sat", label: "Saturday" },
  { value: 6, short: "Sun", label: "Sunday" },
] as const;

export const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];

/** Koniec aktívneho okna v minútach dňa — 02:30 nasledujúceho dňa. */
export const DAY_END_MIN = 26 * 60 + 30;

/** Medze, ktoré musia sedieť s CHECK-om v migrácii 022. */
export const MIN_DURATION = 5;
export const MAX_DURATION = 600;
export const MIN_PACE = 0.1;
export const MAX_PACE = 6;
export const MAX_ACTIVITIES = 60;
export const MAX_TEXT = 200;

export type ScheduleActivity = {
  place: Place;
  what: string;
  pace: number;
  min_minutes: number;
  max_minutes: number;
  arrival: string;
  days: number[];
};

export type ScheduleRow = {
  model_id: string;
  wake_weekday_start_min: number;
  wake_weekday_end_min: number;
  wake_weekend_start_min: number;
  wake_weekend_end_min: number;
  night_place: Place;
  night_what: string;
  night_pace: number | string;
  night_arrival: string;
  activities: ScheduleActivity[];
};

export const SCHEDULE_COLUMNS =
  "model_id, wake_weekday_start_min, wake_weekday_end_min, wake_weekend_start_min, " +
  "wake_weekend_end_min, night_place, night_what, night_pace, night_arrival, activities";

/** Nová položka, ktorú klient dostane po kliknutí na „Add". */
export function blankActivity(): ScheduleActivity {
  return {
    place: "home",
    what: "",
    pace: 1,
    min_minutes: 45,
    max_minutes: 90,
    arrival: "",
    days: [...ALL_DAYS],
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function isPlace(value: unknown): value is Place {
  return typeof value === "string" && (PLACES as readonly string[]).includes(value);
}

/**
 * Jedna položka do tvaru, ktorý databáza prijme. `null` = nepoužiteľná.
 *
 * Beží aj na serveri (pred zápisom), aj v editore (pred ukážkou), takže sa
 * nikdy nestane, že klient vidí niečo iné, než sa uloží.
 */
export function normaliseActivity(raw: unknown): ScheduleActivity | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;

  const what = String(item.what ?? "").trim().slice(0, MAX_TEXT);
  if (!what) return null;

  const paceRaw = Number(item.pace);
  const minRaw = Number(item.min_minutes);
  const maxRaw = Number(item.max_minutes);

  let low = Number.isFinite(minRaw) ? Math.round(minRaw) : 30;
  let high = Number.isFinite(maxRaw) ? Math.round(maxRaw) : 60;
  low = clamp(low, MIN_DURATION, MAX_DURATION);
  high = clamp(high, MIN_DURATION, MAX_DURATION);
  if (high < low) [low, high] = [high, low];

  const days = ALL_DAYS.filter((day) =>
    Array.isArray(item.days) ? item.days.map(Number).includes(day) : false,
  );

  return {
    place: isPlace(item.place) ? item.place : "home",
    what,
    pace: Number.isFinite(paceRaw) ? clamp(paceRaw, MIN_PACE, MAX_PACE) : 1,
    min_minutes: low,
    max_minutes: high,
    arrival: String(item.arrival ?? "").trim().slice(0, MAX_TEXT),
    // Bez jediného dňa by to bola činnosť, ktorá sa nikdy nestane — a DB by
    // taký riadok aj tak odmietla.
    days: days.length > 0 ? days : [...ALL_DAYS],
  };
}

export function normaliseActivities(raw: unknown): ScheduleActivity[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(normaliseActivity)
    .filter((item): item is ScheduleActivity => item !== null)
    .slice(0, MAX_ACTIVITIES);
}

/* --------------------------------------------------------------------------
   Ukážka dňa
--------------------------------------------------------------------------- */

export type PreviewBlock = {
  from: number;
  to: number;
  place: Place;
  what: string;
  pace: number;
  arrival: string;
};

/**
 * Malý deterministický generátor (mulberry32). Nie je to ten istý generátor
 * ako v Pythone a ani nemá byť: presné minúty sa losujú každý deň nanovo, tak
 * by rovnaké čísla boli sľub, ktorý sa nedá dodržať. Ukážka má ukázať TVAR
 * dňa — poradie, miesta, zhruba kedy a ako dlho — a ten sedí presne.
 */
function rng(seed: string): () => number {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  let state = hash >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function between(next: () => number, low: number, high: number): number {
  if (high < low) [low, high] = [high, low];
  return low + Math.floor(next() * (high - low + 1));
}

/**
 * Príklad jedného dňa — tá istá skladačka ako `den.plan()`: vstane niekedy
 * v okne, činnosti idú v poradí a každá trvá náhodne dlho v svojom rozsahu,
 * a čo sa do okna nezmestí, sa už nestane. Noc dobehne do 02:30.
 */
export function previewDay(
  row: {
    wake_weekday_start_min: number;
    wake_weekday_end_min: number;
    wake_weekend_start_min: number;
    wake_weekend_end_min: number;
    night_place: Place;
    night_what: string;
    night_pace: number;
    night_arrival: string;
    activities: ScheduleActivity[];
  },
  weekday: number,
  seed = "preview",
): PreviewBlock[] {
  const next = rng(`${seed}:${weekday}`);
  const weekend = weekday >= 5;
  let cursor = between(
    next,
    weekend ? row.wake_weekend_start_min : row.wake_weekday_start_min,
    weekend ? row.wake_weekend_end_min : row.wake_weekday_end_min,
  );

  const blocks: PreviewBlock[] = [];
  for (const activity of row.activities) {
    if (!activity.days.includes(weekday)) continue;
    const length = between(next, activity.min_minutes, activity.max_minutes);
    if (cursor + length >= DAY_END_MIN) break;
    blocks.push({
      from: cursor,
      to: cursor + length,
      place: activity.place,
      what: activity.what,
      pace: activity.pace,
      arrival: activity.arrival,
    });
    cursor += length;
  }

  if (cursor < DAY_END_MIN && row.night_what.trim()) {
    blocks.push({
      from: cursor,
      to: DAY_END_MIN,
      place: row.night_place,
      what: row.night_what,
      pace: row.night_pace,
      arrival: row.night_arrival,
    });
  }
  return blocks;
}

/** `1590` → `02:30`. Minúty môžu presiahnuť polnoc, preto vlastná funkcia. */
export function clockLabel(minutes: number): string {
  const safe = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

/** „1 h 20 m" — trvanie, ktoré sa dá prečítať bez počítania. */
export function durationLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  if (hours === 0) return `${rest} min`;
  if (rest === 0) return `${hours} h`;
  return `${hours} h ${rest} min`;
}

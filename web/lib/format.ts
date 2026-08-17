/** Formátovanie čísel a času pre UI (client-safe). Všetko v en-US. */

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const USD_PRECISE = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

/** `$12.40`. Supabase vracia numeric ako string — prijmeme oboje. */
export function usd(value: number | string | null | undefined): string {
  return USD.format(toNumber(value));
}

/** Drobné sumy (jedna odpoveď stojí centy) potrebujú viac desatinných miest. */
export function usdPrecise(value: number | string | null | undefined): string {
  const n = toNumber(value);
  return n !== 0 && Math.abs(n) < 0.01 ? USD_PRECISE.format(n) : USD.format(n);
}

export function toNumber(value: number | string | null | undefined): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact" });

export function compactNumber(value: number): string {
  return value >= 10_000 ? COMPACT.format(value) : String(value);
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** „3 min ago", „yesterday", „12 Aug". */
export function relativeTime(input: string | Date | null | undefined): string {
  if (!input) return "never";
  const date = typeof input === "string" ? new Date(input) : input;
  const ms = date.getTime();
  if (!Number.isFinite(ms)) return "never";

  const diff = Date.now() - ms;
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} min ago`;
  if (diff < DAY) {
    const hours = Math.floor(diff / HOUR);
    return `${hours} h ago`;
  }
  if (diff < 2 * DAY) return "yesterday";
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)} days ago`;
  return date.toLocaleDateString("en-US", { day: "numeric", month: "short" });
}

/** `Aug 17, 2026 · 14:32` */
export function dateTime(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const date = typeof input === "string" ? new Date(input) : input;
  if (!Number.isFinite(date.getTime())) return "—";
  return `${date.toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })} · ${date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
}

/**
 * ISO timestamp N dní dozadu. Obal nad `Date.now()` je zámerný — v tele
 * komponentu by React Compiler (správne) hlásil nečistú funkciu v renderi.
 */
export function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * DAY).toISOString();
}

/** Je časová značka už za nami? (obal nad `Date.now()` — viď `isoDaysAgo`) */
export function isPast(input: string | null | undefined): boolean {
  if (!input) return false;
  const ms = new Date(input).getTime();
  return Number.isFinite(ms) && ms < Date.now();
}

/** Je časová značka mladšia než `maxAgeMs`? */
export function isRecent(input: string | null | undefined, maxAgeMs: number): boolean {
  if (!input) return false;
  const ms = new Date(input).getTime();
  return Number.isFinite(ms) && Date.now() - ms < maxAgeMs;
}

/** `732` → `12:12` — behavior drží aktívne okno v minútach od polnoci. */
export function minutesToHhMm(minutes: number): string {
  const safe = ((Math.round(minutes) % 1440) + 1440) % 1440;
  const h = String(Math.floor(safe / 60)).padStart(2, "0");
  const m = String(safe % 60).padStart(2, "0");
  return `${h}:${m}`;
}

/** `12:12` → `732`; nezmysel vráti null, nech sa neuloží ticho zlá hodnota. */
export function hhMmToMinutes(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (h > 23 || m > 59) return null;
  return h * 60 + m;
}

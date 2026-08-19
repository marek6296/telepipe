/**
 * Jazyky modelky — katalóg a tvar nastavenia.
 *
 * DVE KÓPIE, NIE TRI. Ten istý zoznam žije vo `worker/src/jazyky.py`, kde sa
 * prekladá do promptu. Databáza ho ZÁMERNE nepozná — CHECK constraint stráži
 * len tvar (kód, úroveň, počet, duplicity), lebo tretia kópia by sa rozišla
 * ako prvá. Keď pribudne jazyk, pribudne na oboch miestach a `npm run
 * test:languages` overí, že sa kódy nerozišli.
 *
 * Klientsky bezpečné — žiadny server import.
 */

export type Language = { code: string; name: string };

export const LANGUAGES: Language[] = [
  { code: "en", name: "English" },
  { code: "de", name: "German" },
  { code: "es", name: "Spanish" },
  { code: "fr", name: "French" },
  { code: "it", name: "Italian" },
  { code: "pt", name: "Portuguese" },
  { code: "nl", name: "Dutch" },
  { code: "pl", name: "Polish" },
  { code: "cs", name: "Czech" },
  { code: "sk", name: "Slovak" },
  { code: "ru", name: "Russian" },
  { code: "uk", name: "Ukrainian" },
  { code: "tr", name: "Turkish" },
  { code: "sv", name: "Swedish" },
  { code: "no", name: "Norwegian" },
  { code: "da", name: "Danish" },
  { code: "fi", name: "Finnish" },
  { code: "ro", name: "Romanian" },
  { code: "hu", name: "Hungarian" },
  { code: "el", name: "Greek" },
  { code: "ar", name: "Arabic" },
  { code: "ja", name: "Japanese" },];

/**
 * Úrovne podľa CEFR. Popis je to, čo klient naozaj potrebuje vedieť — nie
 * definícia z učebnice, ale čo to spraví s jej odpoveďami.
 */
export const LEVELS = [
  { value: "A1", label: "A1 — a few words" },
  { value: "A2", label: "A2 — basics, simple sentences" },
  { value: "B1", label: "B1 — gets by, makes small mistakes" },
  { value: "B2", label: "B2 — good, not native" },
  { value: "C1", label: "C1 — very good" },
  { value: "C2", label: "C2 — basically native" },
] as const;

export type Level = (typeof LEVELS)[number]["value"];

export const DEFAULT_PRIMARY = "en";
export const DEFAULT_LEVEL: Level = "B1";
/** Koľko ďalších jazykov si smie navoliť. Rovnaké číslo stráži CHECK v DB. */
export const MAX_EXTRA = 3;

export type ExtraLanguage = { code: string; level: Level };

export function languageName(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.name ?? code;
}

export function isKnownLanguage(code: string): boolean {
  return LANGUAGES.some((l) => l.code === code);
}

export function isLevel(value: string): value is Level {
  return LEVELS.some((l) => l.value === value);
}

/**
 * Očistí, čo prišlo z formulára alebo z databázy.
 *
 * Nikdy nehádže: prompt sa kvôli jednému pokazenému riadku nesmie prestať
 * skladať a formulár sa kvôli nemu nesmie prestať vykresliť. Čo nedáva zmysel,
 * ticho vypadne — a keďže to isté robí aj worker, obe strany skončia rovnako.
 */
export function normalizeExtra(raw: unknown, primary: string): ExtraLanguage[] {
  if (!Array.isArray(raw)) return [];
  const out: ExtraLanguage[] = [];
  const seen = new Set<string>([primary]);

  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const code = String((item as { code?: unknown }).code ?? "").trim().toLowerCase();
    const level = String((item as { level?: unknown }).level ?? "").trim().toUpperCase();
    if (!isKnownLanguage(code) || seen.has(code) || !isLevel(level)) continue;
    seen.add(code);
    out.push({ code, level });
    if (out.length >= MAX_EXTRA) break;
  }
  return out;
}

export function normalizePrimary(raw: unknown): string {
  const code = String(raw ?? "").trim().toLowerCase();
  return isKnownLanguage(code) ? code : DEFAULT_PRIMARY;
}

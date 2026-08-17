/**
 * Typy agentov — jediný register, z ktorého čerpá celé /app.
 *
 * Klient si typ volí pri založení modelky a už ho nemení (migrácia 018:
 * `models.model_type`, bez update grantu). Typ rozhoduje o tom, ktoré karty
 * modelka vôbec má — Fanvue je vec `persona` agenta a firemný ho mať nikdy
 * nebude.
 *
 * Súbor je client-safe: žiadny server import, žiadne ikony. Ikony si drží
 * komponent, ktorý ich kreslí — tento modul je dáta.
 *
 * PRAVIDLO: nový typ = jeden riadok v `MODEL_TYPES` + jeden riadok v
 * `MODEL_TYPE_TABS`. Ak sa niekde v UI objaví `if (type === "persona")`, je to
 * chyba tohto súboru, nie toho miesta.
 */

export type ModelType = "persona" | "business" | "private";

/** Karty (taby) detailu modelky. Slug = segment v URL `/app/m/[id]/<slug>`. */
export type ModelTabSlug =
  | "telegram"
  | "fanvue"
  | "persona"
  | "behavior"
  | "voice"
  | "photos"
  | "chats";

export type ModelTypeInfo = {
  value: ModelType;
  /** Názov v „Add model" dialógu. */
  label: string;
  /** Krátky štítok na karte modelky a v admin tabuľke. */
  shortLabel: string;
  /** Jedna veta, čo ten agent robí — presne to, čo klient číta pri výbere. */
  description: string;
  /**
   * Dá sa dnes založiť? `false` = „Coming soon", karta je v dialógu vidieť,
   * ale nedá sa vybrať. Musí sedieť s `model_type_enabled()` v DB — tá je
   * skutočná hranica, toto je len to, čo o nej vie prehliadač.
   */
  enabled: boolean;
};

export const MODEL_TYPES: readonly ModelTypeInfo[] = [
  {
    value: "persona",
    label: "AI Persona Agent",
    shortLabel: "Persona",
    description:
      "Persona-driven companion that chats on Telegram, sends voice notes and converts fans to your platform.",
    enabled: true,
  },
  {
    value: "business",
    label: "AI Business Agent",
    shortLabel: "Business",
    description:
      "Replies on behalf of your company — support, sales and FAQs in your brand voice.",
    enabled: false,
  },
  {
    value: "private",
    label: "AI Private Agent",
    shortLabel: "Private",
    description: "Your personal assistant that answers your own chats the way you would.",
    enabled: false,
  },
] as const;

/** Predvoľba v dialógu — prvý typ, ktorý sa naozaj dá založiť. */
export const DEFAULT_MODEL_TYPE: ModelType = "persona";

/**
 * Typ → karty, ktoré preň dávajú zmysel. Poradie je poradie v tab bare.
 *
 * `business`/`private` tu už majú svoj riadok, hoci sa zatiaľ nedajú založiť:
 * až ich niekto pustí, tab bar bude fungovať bez ďalšieho zásahu a rozdiel
 * (žiadne Fanvue, žiadny hlas) je vidieť na jednom mieste.
 */
export const MODEL_TYPE_TABS: Record<ModelType, readonly ModelTabSlug[]> = {
  persona: ["telegram", "fanvue", "persona", "behavior", "voice", "photos", "chats"],
  business: ["telegram", "persona", "behavior", "photos", "chats"],
  private: ["telegram", "persona", "behavior", "chats"],
};

const KNOWN: readonly ModelType[] = MODEL_TYPES.map((type) => type.value);

/** Hodnota z DB je text — zúžime ju na známy typ, nech TS nefňuká. */
export function asModelType(value: string | null | undefined): ModelType {
  return KNOWN.includes(value as ModelType) ? (value as ModelType) : DEFAULT_MODEL_TYPE;
}

export function modelTypeInfo(value: string | null | undefined): ModelTypeInfo {
  const type = asModelType(value);
  return MODEL_TYPES.find((info) => info.value === type) ?? MODEL_TYPES[0];
}

/**
 * Allowlist pre server action. Zámerne sa počíta z `MODEL_TYPES`, aby sa
 * „Coming soon" nedalo obísť tým, že niekto v dev tools prepne `disabled` na
 * karte — akcia pozerá sem, nie na to, čo prišlo z prehliadača.
 */
export function isModelTypeEnabled(value: string | null | undefined): boolean {
  return MODEL_TYPES.some((info) => info.value === value && info.enabled);
}

/** Má tento typ takúto kartu? Jediný test, ktorý smie UI robiť. */
export function modelTypeHasTab(
  value: string | null | undefined,
  slug: ModelTabSlug,
): boolean {
  return MODEL_TYPE_TABS[asModelType(value)].includes(slug);
}

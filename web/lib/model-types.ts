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
 * `MODEL_TYPE_TABS` (a v `MODEL_TYPE_SUBTABS`, ak má aj podkarty). Ak sa niekde
 * v UI objaví `if (type === "persona")`, je to chyba tohto súboru, nie toho
 * miesta.
 */

export type ModelType = "persona" | "business" | "private";

/** Karty (taby) detailu modelky. Slug = segment v URL `/app/m/[id]/<slug>`. */
export type ModelTabSlug = "telegram" | "fanvue" | "instagram" | "persona" | "voice";

/**
 * Karty, ktoré vidí LEN superadmin.
 *
 * Instagram je zatiaľ vo výstavbe a testuje sa na vlastných účtoch — kým Meta
 * neschváli appke Advanced Access, cudzí účet sa aj tak pripojiť nedá. Skrytá
 * karta ale NIE JE hranica: rovnaká kontrola beží aj v `requireModelTab` a
 * v obidvoch API routách, lebo adresu si vie ktokoľvek napísať sám.
 */
export const SUPERADMIN_TABS: readonly ModelTabSlug[] = ["instagram"];

export function tabIsSuperadminOnly(slug: ModelTabSlug): boolean {
  return SUPERADMIN_TABS.includes(slug);
}

/**
 * Podkarty jednej karty. Slug je druhý segment URL, `index` je samotná karta
 * (`/app/m/[id]/telegram` = Connection, `/app/m/[id]/fanvue` = Connect,
 * `/app/m/[id]/persona` = Identity) — nie redirect na `/connection`, aby staré
 * odkazy aj návrat z Fanvue OAuth (`?error=`) pristáli presne tam, kde predtým.
 */
export type ModelSubTabSlug =
  | "index"
  | "settings"
  | "photos"
  | "chats"
  /** Control bot: čo má hlásiť do Telegramu majiteľovi. */
  | "bot"
  | "behavior"
  | "day";

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
  persona: ["telegram", "fanvue", "instagram", "persona", "voice"],
  business: ["telegram", "persona"],
  private: ["telegram", "persona"],
};

/**
 * Typ → karta → podkarty. Poradie je poradie v druhom (tichšom) tab bare.
 *
 * Fotky aj konverzácie sedia pod Telegramom zámerne: fotky odchádzajú len tam
 * a `dm_users`/`dm_messages` je telegramová história. Fanvue má svoje vlastné
 * fotky (vault) aj svoje vlastné konverzácie (`fv_users`/`fv_messages`) — sú to
 * dvaja agenti, nie dva pohľady na to isté.
 *
 * Persona, Behavior a Daily life sú jedna karta z toho istého dôvodu: persona
 * je, KTO je, chovanie je, AKO sa správa, a deň je, KDE je — tá istá osoba
 * z troch strán. Rozdeliť ich do troch tabov znamenalo trikrát otvárať to isté.
 *
 * Prečo je deň VLASTNÁ podkarta a nie ďalšia sekcia Identity: Identity je
 * formulár s textami, ktoré sa píšu raz; deň je zoznam, ktorý sa pridáva, maže
 * a preusporadúva, a k tomu ukážka vygenerovaného dňa. Simona ich má tridsaťdeväť
 * — pod Identity by to bola dlhá obrazovka s dvoma nesúvisiacimi režimami práce.
 *
 * Karta bez riadku tu podkarty nemá a druhý tab bar sa jej nevykreslí (Voice).
 * Rozdiely medzi typmi ostávajú na jednom mieste: osobný agent fotky neposiela,
 * tak ich pod Telegramom ani nemá.
 */
export const MODEL_TYPE_SUBTABS: Record<
  ModelType,
  Partial<Record<ModelTabSlug, readonly ModelSubTabSlug[]>>
> = {
  persona: {
    telegram: ["index", "settings", "bot", "photos", "chats"],
    fanvue: ["index", "settings", "photos", "chats"],
    // Instagram má zatiaľ len pripojenie a nastavenia — konverzácie pribudnú
    // s agentom vo workeri.
    instagram: ["index", "settings"],
    persona: ["index", "behavior", "day"],
  },
  business: {
    telegram: ["index", "settings", "bot", "photos", "chats"],
    // Firemný agent nemá denný život: firma nechodí do posilňovne a jej
    // odpovede sa nemajú spomaľovať tým, že „je na fotení".
    persona: ["index", "behavior"],
  },
  private: {
    telegram: ["index", "settings", "chats"],
    persona: ["index", "behavior"],
  },
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

/** Podkarty danej karty pre daný typ. Prázdne pole = druhý tab bar netreba. */
export function modelTypeSubTabs(
  value: string | null | undefined,
  tab: ModelTabSlug,
): readonly ModelSubTabSlug[] {
  if (!modelTypeHasTab(value, tab)) return [];
  return MODEL_TYPE_SUBTABS[asModelType(value)][tab] ?? [];
}

/**
 * Má tento typ takúto podkartu? Kontroluje aj rodičovskú kartu — `/fanvue/chats`
 * na firemnom agentovi musí padnúť rovnako ako `/fanvue`.
 */
export function modelTypeHasSubTab(
  value: string | null | undefined,
  tab: ModelTabSlug,
  sub: ModelSubTabSlug,
): boolean {
  return modelTypeSubTabs(value, tab).includes(sub);
}

/**
 * Z cesty `/app/m/<id>/<tab>/<sub>/…` vytiahne, kde klient stojí.
 *
 * `sub: null` znamená „druhý segment podkartou nie je" — `/persona/build` je
 * sprievodca, teda tok, nie záložka, a nesmie podfarbiť „Identity", akoby na
 * nej klient stál. Logika je tu (nie v komponente), lebo je to to isté pravidlo
 * ako `MODEL_TYPE_SUBTABS` a dá sa overiť bez prehliadača.
 */
export function activeModelTab(
  pathname: string,
  modelId: string,
  modelType: string | null | undefined,
): {
  tab: ModelTabSlug | null;
  sub: ModelSubTabSlug | null;
  subTabs: readonly ModelSubTabSlug[];
} {
  const prefix = `/app/m/${modelId}/`;
  const rest = pathname.startsWith(prefix) ? pathname.slice(prefix.length).split("/") : [];
  const tab = MODEL_TYPE_TABS[asModelType(modelType)].find((slug) => slug === rest[0]) ?? null;
  if (!tab) return { tab: null, sub: null, subTabs: [] };

  const subTabs = modelTypeSubTabs(modelType, tab);
  const sub = rest[1]
    ? (subTabs.find((slug) => slug !== "index" && slug === rest[1]) ?? null)
    : "index";
  return { tab, sub, subTabs };
}

/** URL podkarty. `index` je samotná karta — bez druhého segmentu. */
export function subTabHref(
  modelId: string,
  tab: ModelTabSlug,
  sub: ModelSubTabSlug,
): string {
  return sub === "index"
    ? `/app/m/${modelId}/${tab}`
    : `/app/m/${modelId}/${tab}/${sub}`;
}

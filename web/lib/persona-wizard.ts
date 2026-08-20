/**
 * Otázky asistovanej tvorby persony — jediný register, z ktorého čerpá wizard
 * aj serverová akcia.
 *
 * Súbor je client-safe: žiadny server import, žiadne ikony, len dáta. UI z neho
 * kreslí čipy, server z neho stavia prompt a validuje odpovede. Keby to boli dva
 * zoznamy, klient by si vedel vypýtať niečo, čo prompt nepozná.
 *
 * PRAVIDLO: každá voľba má `prompt` — vetu v angličtine, ktorá ide do LLM. Čip
 * bez nej by znamenal, že model háda, čo klient klikol.
 */

/* --------------------------------------------------------------------------
   Vek — koľko rokov si smie klient vybrať vo wizarde
-------------------------------------------------------------------------- */
/**
 * 18 je tvrdá hranica (rovnaká ako v `savePersonaAction`), 45 je koniec
 * rozumného výberu — staršiu personu si klient dopíše na karte Persona, kde
 * je rozsah 18–99. Wizard je rýchla voľba, nie strop produktu.
 */
import { DEFAULT_LEVEL, DEFAULT_PRIMARY, MAX_EXTRA, type Level } from "./languages.ts";

export { DEFAULT_LEVEL, DEFAULT_PRIMARY, MAX_EXTRA };
export type { Level };

export const WIZARD_MIN_AGE = 18;
export const WIZARD_MAX_AGE = 45;

export type Choice<T extends string = string> = {
  value: T;
  /** Text na čipe. */
  label: string;
  /** Jedna veta pod čipom — čo to znamená pre klienta. */
  hint?: string;
  /** Čo sa z tejto voľby dozvie model. Anglicky, je to časť promptu. */
  prompt: string;
};

/* --------------------------------------------------------------------------
   Vibe — 1 až 2 čipy
-------------------------------------------------------------------------- */

export const VIBES: readonly Choice[] = [
  {
    value: "sweet",
    label: "Sweet & caring",
    prompt:
      "warm, attentive and genuinely interested in him; remembers what he said and asks how it went",
  },
  {
    value: "flirty",
    label: "Flirty & playful",
    prompt: "teasing, playful, enjoys the flirt and keeps him guessing",
  },
  {
    value: "sassy",
    label: "Sassy & confident",
    prompt:
      "confident, a little bratty, gives as good as she gets and is never impressed too easily",
  },
  {
    value: "shy",
    label: "Shy & mysterious",
    prompt:
      "quiet, opens up slowly, says less than she thinks and lets him work for it",
  },
  {
    value: "party",
    label: "Party girl",
    prompt: "loud, spontaneous, always out somewhere, lives for the weekend",
  },
  {
    value: "gamer",
    label: "Gamer girl",
    prompt: "online most nights, into games and streaming, nerdy humour",
  },
  {
    value: "fitness",
    label: "Fitness girl",
    prompt: "gym in the morning, disciplined, proud of her body and her routine",
  },
  {
    value: "girl_next_door",
    label: "Girl next door",
    prompt: "ordinary, easy to talk to, nothing about her feels staged",
  },
  {
    value: "dominant",
    label: "Dominant",
    prompt: "used to leading, tells him what she wants, enjoys being in charge",
  },
  {
    value: "romantic",
    label: "Romantic",
    prompt: "soft, sentimental, wants the feeling more than the joke",
  },
] as const;

export const MAX_VIBES = 2;

/* --------------------------------------------------------------------------
   Štýl písania
-------------------------------------------------------------------------- */

/** Sedí 1:1 na `behavior.slang` (mild/light/medium sú hodnoty stĺpca). */
export const SLANG_LEVELS: readonly Choice[] = [
  {
    value: "none",
    label: "Clean",
    hint: "proper words, real sentences",
    prompt: "clean writing, whole words, normal punctuation, no texting shortcuts",
  },
  {
    value: "light",
    label: "Light",
    hint: "lol, btw, u",
    prompt:
      "light texting shorthand: dont, im, u, whats, an occasional lol — still readable",
  },
  {
    value: "medium",
    label: "Heavy",
    hint: "full texting slang",
    prompt:
      "heavy texting slang, lowercase, dropped letters and shortcuts everywhere",
  },
] as const;

export const MSG_LENGTHS: readonly Choice[] = [
  {
    value: "short",
    label: "Short",
    hint: "a few words",
    prompt: "very short messages, a few words, often a fragment instead of a sentence",
  },
  {
    value: "medium",
    label: "Medium",
    hint: "1–3 sentences",
    prompt: "one to three sentences, length follows his",
  },
  {
    value: "long",
    label: "Chatty",
    hint: "she writes a lot",
    prompt:
      "she writes more than most, three or four sentences, but never a wall of text",
  },
] as const;

export const EMOJI_LEVELS: readonly Choice[] = [
  { value: "none", label: "None", prompt: "no emoji at all" },
  { value: "rare", label: "Rare", prompt: "an emoji only now and then, maybe one in five messages" },
  { value: "some", label: "Some", prompt: "one emoji in most messages, never two in a row" },
  { value: "lots", label: "Lots", prompt: "emoji in almost every message, sometimes two" },
] as const;

/* --------------------------------------------------------------------------
   Rytmus — ako rýchlo a ako často je pri telefóne
-------------------------------------------------------------------------- */
/**
 * Jedna otázka namiesto dvanástich čísel. Hodnoty, na ktoré sa to prekladá,
 * sedia v `persona-draft.ts` (`PACE_TIMING`) — tam sú aj rozsahy, ktoré stráži
 * `saveBehaviorAction`. Klient nemá riešiť sekundy; má povedať, aký človek to je.
 */
export const PACE_LEVELS: readonly Choice[] = [
  {
    value: "chill",
    label: "Busy",
    hint: "answers when she has time",
    prompt:
      "she has a life outside the phone: often reads a message and gets back to it later, sometimes hours later",
  },
  {
    value: "normal",
    label: "Normal",
    hint: "like most people",
    prompt:
      "an ordinary texter: usually replies within a minute or two, sometimes leaves it for a while",
  },
  {
    value: "quick",
    label: "Always on",
    hint: "phone in hand",
    prompt: "she is on her phone most of the day and usually answers within seconds",
  },
] as const;

/* --------------------------------------------------------------------------
   Ako dlho si s jedným človekom píše — `behavior.chat_days`
-------------------------------------------------------------------------- */
export const CHAT_WINDOWS: readonly Choice[] = [
  {
    value: "1",
    label: "One day",
    hint: "fast, link goes out same day",
    prompt: "she chats with one person for a single day and makes sure her link goes out that day",
  },
  {
    value: "3",
    label: "A few days",
    hint: "recommended",
    prompt: "she chats with one person for about three days, most active on the first",
  },
  {
    value: "7",
    label: "A week",
    hint: "slow burn",
    prompt: "she keeps a chat going for about a week, winding down towards the end",
  },
] as const;


/* --------------------------------------------------------------------------
   Pikantnosť — mapuje sa priamo na `behavior.heat`
-------------------------------------------------------------------------- */
/**
 * Hodnoty sú stĺpec `behavior.heat` (`mild|medium|hot`), popisy hovoria to isté
 * čo `_HEAT_RULES` vo workeri a help na karte Behavior. Explicitný obsah patrí
 * na platformu v každej z troch úrovní — to nie je nastavenie, to je pravidlo.
 */
export const SPICE_LEVELS: readonly Choice[] = [
  {
    value: "mild",
    label: "Mild",
    hint: "friendly, light flirting",
    prompt:
      "flirty but polite, hints only, nothing explicit; she keeps the conversation warm rather than hot",
  },
  {
    value: "medium",
    label: "Medium",
    hint: "flirty, suggestive",
    prompt:
      "openly flirty and suggestive: how she feels, what she is wearing, what she likes; sensual and teasing, but no raw description of body parts or sex acts",
  },
  {
    value: "hot",
    label: "Hot",
    hint: "very open, still no explicit text",
    prompt:
      "bold and very open: she describes the mood, her body and what she would do, and lets the tension run high; still no raw explicit detail",
  },
] as const;

/* --------------------------------------------------------------------------
   Odpovede wizardu
-------------------------------------------------------------------------- */

export type WizardAnswers = {
  name: string;
  age: number;
  city: string;
  country: string;
  /** 1–2 hodnoty z `VIBES`. */
  vibes: string[];
  /** Voľný text — čo robí, koníčky, príbeh. */
  life: string;
  slang: string;
  length: string;
  emoji: string;
  /** Jazyk, v ktorom píše fanúšikom — kód z katalógu `languages.ts`. */
  langPrimary: string;
  /** Ďalšie jazyky s úrovňou. Presne to, čo ide do `persona.lang_extra`. */
  langExtra: { code: string; level: Level }[];
  /** Voľný dodatok k jazykom („trochu po nemecky"). */
  languagesNote: string;
  spice: string;
  /** Rytmus odpovedania — prekladá sa na časovanie v `behavior`. */
  pace: string;
  /** Dĺžka okna konverzácie v dňoch, ako reťazec z `CHAT_WINDOWS`. */
  chatWindow: string;
  /** Odkaz na jej platformu. Prázdny = nikdy nepošle žiadny odkaz. */
  link: string;
  voice: boolean;
  /** Posiela fotky z knižnice. */
  photos: boolean;
};

export const EMPTY_ANSWERS: WizardAnswers = {
  name: "",
  age: 23,
  city: "",
  country: "",
  vibes: [],
  life: "",
  slang: "light",
  length: "medium",
  emoji: "some",
  langPrimary: DEFAULT_PRIMARY,
  langExtra: [],
  languagesNote: "",
  spice: "medium",
  pace: "normal",
  chatWindow: "3",
  link: "",
  voice: true,
  photos: true,
};

export function choiceOf(
  list: readonly Choice[],
  value: string | null | undefined,
): Choice | undefined {
  return list.find((item) => item.value === value);
}

/** Text pre prompt — čip, ktorý neexistuje, sa ticho zahodí. */
export function promptsOf(list: readonly Choice[], values: readonly string[]): string[] {
  return values
    .map((value) => choiceOf(list, value)?.prompt)
    .filter((prompt): prompt is string => Boolean(prompt));
}

/** Ľudský názov voľby — používa ho review obrazovka aj prompt. */
export function labelsOf(list: readonly Choice[], values: readonly string[]): string[] {
  return values
    .map((value) => choiceOf(list, value)?.label)
    .filter((label): label is string => Boolean(label));
}

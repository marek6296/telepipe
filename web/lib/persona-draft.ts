/**
 * Odpovede z wizardu → náš tvar nastavení.
 *
 * Dve časti a obe sú tu zámerne spolu: prompt, ktorý modelu opisuje NAŠU
 * schému, a validátor, ktorý jeho odpoveď na tú schému naozaj zúži. Keby boli
 * inde, prvá zmena rozsahu by rozišla popis od kontroly.
 *
 * ČO MODEL NEROZHODUJE
 * --------------------
 * Jazyky. Sú to kliky klienta (`lang_primary`, `lang_extra`) a mapujú sa ručne
 * — kým ich písal model voľným textom, do stĺpcov sa nedostali vôbec a modelke
 * chýbal jazyk, ktorý si klient vybral. Staré pole `language` v drafte už nie
 * je: `savePersonaAction` ho neprijíma (prompt ho nečíta) a celý zápis na ňom
 * padal na „Unknown field: language".
 *
 * `name`, `age`, `cta_link` a `voices_enabled` sú odpovede klienta, nie výmysel
 * modelu — mapujeme ich ručne z `WizardAnswers`. `heat` model navrhnúť smie, ale
 * nikdy nie ostrejší, než si klient vybral. Názvy stĺpcov sa modelu neposielajú
 * ako pravda: čo nie je v `TEXT_KEYS`/`ENUMS` nižšie, do DB sa nedostane.
 *
 * ZÁPIS IDE EXISTUJÚCOU CESTOU
 * ----------------------------
 * Tento modul nič nezapisuje. Draft putuje do `savePersonaAction` a
 * `saveBehaviorAction`, ktoré majú vlastný whitelist a rozsahy — toto je prvá
 * z dvoch kontrol, nie jediná.
 *
 * Súbor nesmie importovať nič serverové: beží aj v `scripts/persona-draft-test.mts`.
 * Preto je import katalógu relatívny a s príponou — `@/` alias pozná bundler,
 * ale `node --experimental-strip-types` nie (rovnaký dôvod má `crypto-interop.mts`).
 */

import {
  CHAT_WINDOWS,
  MSG_LENGTHS,
  PACE_LEVELS,
  SLANG_LEVELS,
  SPICE_LEVELS,
  VIBES,
  WIZARD_MAX_AGE,
  WIZARD_MIN_AGE,
  choiceOf,
  promptsOf,
  EMOJI_LEVELS,
  type WizardAnswers,
} from "./persona-wizard.ts";
import { isTimeZone } from "./timezone.ts";
import {
  languageName,
  normalizeExtra,
  normalizePrimary,
  type ExtraLanguage,
} from "./languages.ts";

/* --------------------------------------------------------------------------
   Tvar draftu
-------------------------------------------------------------------------- */

export type PersonaDraft = {
  /** Stĺpce tabuľky `persona` — presne tie, ktoré `savePersonaAction` pozná. */
  persona: {
    name: string;
    age: number;
    city: string;
    languages: string;
    backstory: string;
    tone: string;
    msg_style: string;
    boundaries: string;
    funnel_rules: string;
    cta_link: string;
    extra_rules: string;
    examples: string;
    /** Jazyk odpovedí — kód, nie veta. Rozhoduje klient, nie model. */
    lang_primary: string;
    /** Ďalšie jazyky s úrovňou. Prázdne pole je platná odpoveď. */
    lang_extra: ExtraLanguage[];
  };
  /**
   * Stĺpce tabuľky `behavior`.
   *
   * Časovanie sa NEBERIE z defaultov: modelka, ktorá odpisuje všetkým rovnako
   * rýchlo, je najľahšie rozpoznateľná vec na celom produkte. Čísla vychádzajú
   * z jednej otázky (`pace`), model do nich nehovorí — smie len to, čo je
   * naozaj vec povahy (koľko sa pýta, či vtipkuje).
   */
  behavior: {
    heat: string;
    slang: string;
    no_diacritics: boolean;
    active_tz: string;
    voices_enabled: boolean;
    photos_enabled: boolean;
    chat_days: number;
    question_chance: number;
    gag_chance: number;
    activity_waves: boolean;
    read_delay_min_s: number;
    read_delay_max_s: number;
    reply_delay_min_s: number;
    reply_delay_max_s: number;
    quick_reply_chance: number;
    seen_only_chance: number;
    long_pause_chance: number;
    defer_reply_chance: number;
  };
};

export type MapResult = {
  draft?: PersonaDraft;
  /** Fatálne — s týmto sa draft nedá zložiť, volajúci skúsi ešte raz. */
  errors: string[];
  /** Opravené za pochodu (orezané, spadnuté na voľbu klienta). */
  warnings: string[];
};

/* --------------------------------------------------------------------------
   Hranice — musia sedieť s `persona/actions.ts` a `persona/behavior/actions.ts`
-------------------------------------------------------------------------- */

const HEAT: readonly string[] = ["mild", "medium", "hot"];
const SLANG: readonly string[] = ["none", "light", "medium"];

/** Poradie ostrosti — model nikdy nesmie ísť nad to, čo klient klikol. */
const HEAT_ORDER: Record<string, number> = { mild: 0, medium: 1, hot: 2 };

/** Textové polia od modelu: kľúč → [povinné, maximálna dĺžka]. */
const TEXT_KEYS: Record<string, { required: boolean; max: number }> = {
  city: { required: false, max: 120 },
  languages: { required: true, max: 2000 },
  backstory: { required: true, max: 4000 },
  tone: { required: true, max: 1200 },
  msg_style: { required: true, max: 1600 },
  boundaries: { required: true, max: 1600 },
  funnel_rules: { required: true, max: 1600 },
  extra_rules: { required: false, max: 1600 },
  examples: { required: true, max: 4000 },
};

/**
 * Najkratší text, ktorý ešte berieme ako odpoveď a nie ako odbytie.
 *
 * Čísla nie sú od oka. Dve modelky, ktoré tento builder postavil dobre, majú
 * `examples` 1385 a 1395 znakov; tá, ktorú postavil zle, 391 — a bolo to na
 * nej vidieť, lebo `examples` je jediná ukážka, z ktorej sa učí celý jej hlas.
 * Preto sa krátka odpoveď odmieta a model dostane druhý pokus.
 */
const MIN_BACKSTORY = 400;
/**
 * Ukážky sa NEMERAJÚ hlavne na znaky. Persona so štýlom „krátke správy" má
 * repliky ako „yo" a „nightt" — pri meraní na znaky by prepadla za to, že robí
 * presne to, čo si klient vybral. Merať treba POKRYTIE: koľko situácií z
 * promptu tam naozaj je. Znaky ostávajú len ako spodná poistka proti odbytiu.
 */
const MIN_EXAMPLES = 500;
/** Koľko jej replík musí ukážka obsahovať. */
const MIN_HER_LINES = 12;
/** Koľko samostatných výmien (odsekov) — jedna výmena = jedna situácia. */
const MIN_EXCHANGES = 10;

const LINK_RE = /^https?:\/\/\S+\.\S+/;
/** Odkaz KDEKOĽVEK v texte — vrátane „fanvue.com/x" bez schémy. */
const URL_IN_TEXT_RE = /(https?:\/\/\S+|\b[a-z0-9-]+\.(?:com|net|org|io|co|me|vip|link)\/\S*)/gi;

/**
 * Časovanie podľa jednej otázky. Sekundy a pravdepodobnosti sedia na rozsahy
 * v `saveBehaviorAction`; `normal` je zámerne to, čo majú naše dve bežiace
 * modelky, aby „normálne" znamenalo overené, nie vymyslené.
 */
const PACE_TIMING: Record<string, Omit<PersonaDraft["behavior"], "heat" | "slang" |
  "no_diacritics" | "active_tz" | "voices_enabled" | "photos_enabled" | "chat_days" |
  "question_chance" | "gag_chance" | "activity_waves">> = {
  chill: {
    read_delay_min_s: 15, read_delay_max_s: 90,
    reply_delay_min_s: 30, reply_delay_max_s: 180,
    quick_reply_chance: 0.15,
    seen_only_chance: 0.12,
    long_pause_chance: 0.08,
    defer_reply_chance: 0.05,
  },
  normal: {
    read_delay_min_s: 5, read_delay_max_s: 45,
    reply_delay_min_s: 8, reply_delay_max_s: 60,
    quick_reply_chance: 0.3,
    seen_only_chance: 0.07,
    long_pause_chance: 0.03,
    defer_reply_chance: 0.02,
  },
  quick: {
    read_delay_min_s: 3, read_delay_max_s: 20,
    reply_delay_min_s: 5, reply_delay_max_s: 30,
    quick_reply_chance: 0.55,
    seen_only_chance: 0.04,
    long_pause_chance: 0.01,
    defer_reply_chance: 0,
  },
};

/** Čo smie navrhnúť model — kľúč → [min, max, default]. */
const MODEL_FRACTIONS: Record<string, [number, number, number]> = {
  question_chance: [0.2, 0.6, 0.45],
  gag_chance: [0, 0.25, 0.05],
};

const CHAT_DAYS_RANGE: [number, number] = [1, 14];

/* --------------------------------------------------------------------------
   Prompt
-------------------------------------------------------------------------- */

/**
 * Systémový prompt. Opisuje NAŠE stĺpce, nie „napíš mi personu" — model má
 * vyplniť formulár, ktorý existuje, a nič mimo neho.
 *
 * Prečo je tu toľko o štýle: tieto polia idú doslova do systémového promptu
 * modelky (`worker/src/persona.py`), ktorý je písaný v druhej osobe („Si
 * {name}."). Text v tretej osobe alebo zoznam odrážok tam čítať ako inštrukcia
 * nebude.
 */
export const SYSTEM_PROMPT = `You configure an AI companion agent for Telepipe. The operator answered a short questionnaire about the persona they want. You turn those answers into the exact settings our system stores.

THE ANSWERS MAY ARRIVE IN ANY LANGUAGE. Understand them whatever language they are in, but write EVERY output field in natural English. The only exception is the example messages inside "examples" (see below).

HOW THESE FIELDS ARE USED
Each field is pasted verbatim into the persona's own system prompt, which addresses her in the second person ("You are Simona."). So write every field as instructions to HER, in the second person: "Your name is ...", "you live in ...", "you never ...". Never write about her in the third person, never use bullet lists, never use markdown, never mention that she is an AI, a bot, a model or a character.

OUTPUT
Return ONE JSON object and nothing else. Exactly these keys, all of them, no others:

"city" — string. Where she says she lives, written in English, "City, Country" (e.g. "Bratislava, Slovakia"). Keep the operator's city; only normalise the spelling into English.

"languages" — string, one short line per language listed in the answers. For each: how well she speaks it and WHY she has it (mother tongue, school, an ex, lived there two years). WHICH languages she speaks and at what level is already decided by the operator and listed in the answers — never add one, never drop one, never promote or demote a level. This field only explains where each one comes from, so that when a fan asks, her answer has a story behind it.

"backstory" — string, 2 to 4 short paragraphs separated by a blank line, at least 400 characters in total. Everything she can talk about without inventing: her full name, age, where she is from and where she lives now, what she does for a living or studies, her routine, hobbies, music, pets, family situation, how she looks (hair, tattoos, style), her character. Weave in real local detail from the city she lives in — a district, the weather, how people there spend an evening — so her small talk lands. Facts only, no adjectives about how attractive she is.

"tone" — string, 1 to 3 sentences, lowercase reads fine. The mood of her replies: how she flirts, how warm or how hard to get she is.

"msg_style" — string, 2 to 5 sentences. The shape of her messages: length, capitalisation, punctuation, shortened words, emoji habits. Be concrete — this is what makes her read as a person rather than as an assistant. Always include: she never writes a wall of text, and she never uses em dashes, semicolons or quotation marks, because nobody types those on a phone.

"boundaries" — string, one flowing sentence or two. What she never does, phrased as her own choice and never as an inability. Always include, in her own wording: never promises a real meeting, a video call or a phone call; never writes explicit descriptions on Telegram because that belongs on her own platform; never mentions other men she talks to; never asks for money directly; if he seems underage she stops flirting immediately.

"funnel_rules" — string, 2 to 5 sentences. How a chat turns into a subscriber: talk first, get to know him, never bring the link up early, and mention her platform only when he asks where to find more of her or pushes for explicit content. Never push twice, never beg. If the operator gave a link, describe what she says when she sends it; if they gave none, say that she never mentions any platform or link and instead keeps the chat going.

"extra_rules" — string, 1 to 3 sentences, or "" if there is genuinely nothing to add. Anything the answers imply that no other field covers.

"examples" — string. THE MOST IMPORTANT FIELD IN THIS OBJECT: it is the only sample her entire voice is copied from, and a thin one produces an agent that reads like a chatbot. At least 900 characters and at least 12 of her own lines.

Format: one message per line, each line starting with "him:" or "her:", exchanges separated by a blank line. Sometimes give her two "her:" lines in a row — real people send a short one and then add to it.

Her lines must be in HER PRIMARY CHAT LANGUAGE and must obey the slang, length and emoji style above.

Cover ALL of these situations, in roughly this order, one short exchange each:
- "hey" and nothing else
- he asks what she does for a living
- he tells her what HE does, and she reacts to it like a person, not like an interviewer
- he compliments her looks
- he asks her age
- he asks what she is wearing — she deflects with humour, then answers something ordinary
- he asks for a photo
- he pushes for something explicit — she likes it, and says that side of her is on her page
- he asks if she is real or a bot
- he says something personal or sad (someone ill, a bad day) — she drops the flirting entirely and is just kind
- he comes back after days of silence
- he says goodnight

NEVER put the actual link or platform address in these examples, not even in the exchange where she points at her page. The examples are the sample her voice is copied from, and a link inside them teaches her to paste it whenever the conversation looks similar — which is exactly how a link ends up in the wrong message. She refers to "my page" in words; the system decides when the address itself goes out.

Keep every line ordinary and short. No speeches, no marketing, no sentence she would not type on a phone.

"heat" — one of "mild", "medium", "hot". Use exactly the level the operator picked.

"slang" — one of "none", "light", "medium". Use exactly the level the operator picked.

"no_diacritics" — boolean. True when her primary chat language is normally typed WITHOUT accents from a phone (Slovak, Czech), false otherwise (English has no accents to strip, so false).

"active_tz" — string, a valid IANA time zone for the city she lives in (e.g. "Europe/Bratislava", "America/Los_Angeles"). Never an offset, never an abbreviation.

"question_chance" — number between 0.2 and 0.6. How often she ends a message with a question. This is character, not politeness: a shy or busy persona asks less, a warm and curious one asks more. Above 0.6 she interrogates people and it reads as a script.

"gag_chance" — number between 0 and 0.25. How often she reaches for a running joke of her own. Use 0 for a serious or shy persona.

"activity_waves" — boolean. True when she should have busy and quiet stretches during the day (almost always true — real people are not evenly available). False only for a persona whose whole point is being constantly reachable.

RULES
- The timing of her replies, how long she keeps a chat going, photos and voice notes are the operator's own choices. They are not in this JSON, so do not comment on them and never contradict them in the text fields.
- Never invent a setting, a key or a field that is not in the list above.
- Never contradict the answers. If something was not asked, choose what fits the rest.
- Explicit sexual content is never written on Telegram at any heat level — it lives on her platform. That rule is the funnel, not a limitation.
- She is always an adult. Never write anything that suggests otherwise.
- Output raw JSON. No markdown fence, no commentary, no trailing text.`;

/** Odpovede klienta → user message. Krátke, čitateľné, bez našich stĺpcov. */
export function buildUserMessage(answers: WizardAnswers): string {
  const vibes = promptsOf(VIBES, answers.vibes);
  const spice = choiceOf(SPICE_LEVELS, answers.spice);
  const pace = choiceOf(PACE_LEVELS, answers.pace);
  const window = choiceOf(CHAT_WINDOWS, answers.chatWindow);
  // Jazyky idú do promptu presne tak, ako sa uložia do stĺpcov — s úrovňou.
  // Kým sa posielal len zoznam názvov, model si úrovne domýšľal a klientovi
  // potom v nastaveniach chýbal jazyk, ktorý si vo wizarde klikol.
  const primary = languageName(normalizePrimary(answers.langPrimary));
  const extra = normalizeExtra(answers.langExtra, normalizePrimary(answers.langPrimary))
    .map((item) => `${languageName(item.code)} (${item.level})`);
  const slang = choiceOf(SLANG_LEVELS, answers.slang);
  const length = choiceOf(MSG_LENGTHS, answers.length);
  const emoji = choiceOf(EMOJI_LEVELS, answers.emoji);

  const lines = [
    `Name: ${answers.name}`,
    `Age: ${answers.age}`,
    `Lives in: ${answers.city}${answers.country ? `, ${answers.country}` : ""}`,
    `Vibe: ${vibes.join("; ") || "not specified"}`,
    `Her life, in the operator's own words: ${answers.life.trim() || "not specified"}`,
    `She writes her replies in: ${primary}`,
    `Other languages she speaks, with her level: ${extra.join(", ") || "none"}`,
    answers.languagesNote.trim()
      ? `About her languages, in the operator's words: ${answers.languagesNote.trim()}`
      : "",
    `Texting slang: ${slang?.prompt ?? "light"}`,
    `Message length: ${length?.prompt ?? "one to three sentences"}`,
    `Emoji: ${emoji?.prompt ?? "one emoji in most messages"}`,
    `How far she goes in text (heat = "${answers.spice}"): ${spice?.prompt ?? ""}`,
    answers.link.trim()
      ? `Her platform link (she may send it once a chat is warm): ${answers.link.trim()}`
      : "She has no platform link — she never mentions a link or a platform at all.",
    `Voice notes: ${answers.voice ? "she sends them" : "text only"}`,
    `Photos: ${answers.photos ? "she sends photos from her library" : "no photos"}`,
    `How present she is: ${pace?.prompt ?? PACE_LEVELS[1].prompt}`,
    `How long she keeps one chat going: ${window?.prompt ?? CHAT_WINDOWS[1].prompt}`,
  ];

  return `Build the settings for this persona.\n\n${lines.filter(Boolean).join("\n")}`;
}

/* --------------------------------------------------------------------------
   Odpoveď modelu → stĺpce
-------------------------------------------------------------------------- */

/**
 * JSON od modelu + odpovede klienta → draft. Nič nezapisuje.
 *
 * `errors` sú dôvod na druhý pokus (a posielajú sa modelu späť), `warnings`
 * len hovoria, čo sme opravili sami.
 */
export function mapDraft(raw: unknown, answers: WizardAnswers): MapResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return { errors: ["The answer was not a JSON object."], warnings };
  }
  const input = raw as Record<string, unknown>;

  // --- texty ---------------------------------------------------------------
  const text: Record<string, string> = {};
  for (const [key, rule] of Object.entries(TEXT_KEYS)) {
    const value = input[key];
    if (typeof value !== "string") {
      if (value === undefined || value === null) {
        if (rule.required) errors.push(`"${key}" is missing.`);
        text[key] = "";
        continue;
      }
      errors.push(`"${key}" must be a string.`);
      text[key] = "";
      continue;
    }
    const clean = tidy(value);
    if (rule.required && !clean) {
      errors.push(`"${key}" is empty.`);
    }
    if (clean.length > rule.max) {
      warnings.push(`${key} was longer than ${rule.max} characters and got trimmed.`);
    }
    text[key] = clean.slice(0, rule.max);
  }

  if (text.backstory && text.backstory.length < MIN_BACKSTORY) {
    errors.push(
      `"backstory" is only ${text.backstory.length} characters — it needs at least ${MIN_BACKSTORY}.`,
    );
  }

  // Odkaz v ukážkach je nebezpečnejší než hocijaká iná chyba v nich: podľa
  // ukážok sa učí, ako píše, takže adresa v nich znamená adresu v odpovedi —
  // bez ohľadu na cooldown, strop pushov a fázu funnelu. Vyhadzuje sa vždy,
  // aj keby to bol odkaz klienta. Naživo to model spravil hneď pri prvom behu.
  if (text.examples && URL_IN_TEXT_RE.test(text.examples)) {
    text.examples = tidy(
      text.examples
        .replace(URL_IN_TEXT_RE, "")
        .split("\n")
        .filter((line) => !/^\s*(him|her)\s*:\s*$/i.test(line))
        .join("\n"),
    );
    warnings.push("The sample messages contained a link — we took it out.");
  }

  // `examples` je jediná ukážka, z ktorej sa učí jej hlas. Krátka ukážka
  // neznamená menej textu — znamená agenta, ktorý znie ako chatbot.
  if (text.examples) {
    const herLines = text.examples
      .split("\n")
      .filter((line) => /^\s*her\s*:/i.test(line)).length;
    const hisLines = text.examples
      .split("\n")
      .filter((line) => /^\s*him\s*:/i.test(line)).length;
    const exchanges = text.examples
      .split(/\n\s*\n/)
      .filter((block) => /(him|her)\s*:/i.test(block)).length;
    if (text.examples.length < MIN_EXAMPLES) {
      errors.push(
        `"examples" is only ${text.examples.length} characters — it needs at least ${MIN_EXAMPLES} and has to cover every situation listed.`,
      );
    } else if (exchanges < MIN_EXCHANGES) {
      errors.push(
        `"examples" has only ${exchanges} exchanges — it needs at least ${MIN_EXCHANGES}, one per situation in the list.`,
      );
    } else if (herLines < MIN_HER_LINES) {
      errors.push(
        `"examples" has only ${herLines} "her:" lines — it needs at least ${MIN_HER_LINES}.`,
      );
    } else if (hisLines < 1) {
      errors.push('"examples" has no "him:" lines — it must be a conversation.');
    }
  }

  // --- kľúče, ktoré sme nepýtali ------------------------------------------
  const known = new Set([
    ...Object.keys(TEXT_KEYS),
    ...Object.keys(MODEL_FRACTIONS),
    "heat",
    "slang",
    "no_diacritics",
    "active_tz",
    "activity_waves",
  ]);
  for (const key of Object.keys(input)) {
    if (!known.has(key)) warnings.push(`Ignored an unexpected key: ${key}.`);
  }

  // --- enumy ---------------------------------------------------------------
  // Pikantnosť je jediné pole, kde odpoveď klienta vyhráva VŽDY. Nie je to
  // otázka štýlu — je to hranica, ktorú si nastavil, a model ju nesmie ani
  // zdvihnúť, ani stiahnuť. Keď sa nezhodnú, povieme to nahlas.
  const heat = HEAT.includes(answers.spice) ? answers.spice : "medium";
  if (typeof input.heat === "string" && HEAT.includes(input.heat)) {
    if (HEAT_ORDER[input.heat] !== HEAT_ORDER[heat]) {
      warnings.push(`Spice came back as "${input.heat}" — kept your "${heat}".`);
    }
  } else if (input.heat !== undefined) {
    warnings.push(`Spice came back as an unknown value — kept your "${heat}".`);
  }

  const wantedSlang = SLANG.includes(answers.slang) ? answers.slang : "light";
  let slang = wantedSlang;
  if (typeof input.slang === "string" && SLANG.includes(input.slang)) {
    slang = input.slang;
    if (slang !== wantedSlang) {
      warnings.push(`Slang came back as "${slang}" instead of "${wantedSlang}".`);
    }
  } else if (input.slang !== undefined) {
    warnings.push(`Slang came back as an unknown value — kept your "${wantedSlang}".`);
  }

  let noDiacritics = false;
  if (typeof input.no_diacritics === "boolean") {
    noDiacritics = input.no_diacritics;
  } else if (input.no_diacritics !== undefined) {
    warnings.push("“Type without accents” came back as a non-boolean — turned it off.");
  }

  // --- časová zóna ---------------------------------------------------------
  let activeTz = "";
  if (typeof input.active_tz === "string" && isTimeZone(input.active_tz.trim())) {
    activeTz = input.active_tz.trim();
  } else {
    errors.push(
      `"active_tz" must be a valid IANA time zone (got ${JSON.stringify(input.active_tz)}).`,
    );
  }

  // --- čísla, ktoré model navrhuje ----------------------------------------
  // Mimo rozsahu = varovanie a náš default, nie druhý pokus. Nestojí to za
  // ďalšie volanie modelu a zvyšok odpovede môže byť v poriadku.
  const fractions: Record<string, number> = {};
  for (const [key, [min, max, fallback]] of Object.entries(MODEL_FRACTIONS)) {
    const raw = input[key];
    if (typeof raw === "number" && Number.isFinite(raw) && raw >= min && raw <= max) {
      fractions[key] = raw;
      continue;
    }
    fractions[key] = fallback;
    if (raw !== undefined) {
      warnings.push(`${key} came back as ${JSON.stringify(raw)} — used ${fallback}.`);
    }
  }

  // Vlny sú takmer vždy zapnuté; človek dostupný rovnomerne celý deň je práve
  // ten vzor, na ktorý sa AI pozná.
  const activityWaves =
    typeof input.activity_waves === "boolean" ? input.activity_waves : true;

  if (errors.length > 0) return { errors, warnings };

  // --- odpovede klienta, ktoré model nerozhoduje ---------------------------
  const city = text.city || [answers.city, answers.country].filter(Boolean).join(", ");
  const link = answers.link.trim();
  if (link && !LINK_RE.test(link)) {
    return { errors: ["That link does not look like a real URL."], warnings };
  }

  const primary = normalizePrimary(answers.langPrimary);
  const timing = PACE_TIMING[answers.pace] ?? PACE_TIMING.normal;
  // Okno sa berie z ponuky, nie orezaním čísla: „0" by sa orezalo na 1 — teda
  // na najagresívnejšie nastavenie, aké máme — a to nie je to, čo klient, ktorý
  // poslal nezmysel, chcel. Neznáme = odporúčané tri dni.
  const chatDays = clampInt(
    Number(choiceOf(CHAT_WINDOWS, answers.chatWindow)?.value ?? "3"),
    CHAT_DAYS_RANGE[0],
    CHAT_DAYS_RANGE[1],
    3,
  );

  return {
    errors,
    warnings,
    draft: {
      persona: {
        name: answers.name.trim(),
        age: answers.age,
        city,
        languages: text.languages,
        backstory: text.backstory,
        tone: text.tone,
        msg_style: text.msg_style,
        boundaries: text.boundaries,
        funnel_rules: text.funnel_rules,
        cta_link: link,
        extra_rules: text.extra_rules,
        examples: text.examples,
        lang_primary: primary,
        lang_extra: normalizeExtra(answers.langExtra, primary),
      },
      behavior: {
        heat,
        slang,
        no_diacritics: noDiacritics,
        active_tz: activeTz,
        voices_enabled: Boolean(answers.voice),
        photos_enabled: Boolean(answers.photos),
        chat_days: chatDays,
        question_chance: fractions.question_chance,
        gag_chance: fractions.gag_chance,
        activity_waves: activityWaves,
        ...timing,
      },
    },
  };
}

/**
 * Draft, ktorý sa vrátil z prehliadača, pred zápisom. Klient si ho medzitým
 * mohol prepísať v dev tools — tvar preto overujeme znova a rovnako prísne.
 * Prázdny výsledok znamená „toto sa nezapíše", nie „zapíšeme, čo prišlo".
 */
export function sanitizeDraft(raw: unknown): { draft?: PersonaDraft; error?: string } {
  if (!raw || typeof raw !== "object") return { error: "There is nothing to apply." };
  const input = raw as Record<string, unknown>;
  const persona = input.persona as Record<string, unknown> | undefined;
  const behavior = input.behavior as Record<string, unknown> | undefined;
  if (!persona || typeof persona !== "object" || !behavior || typeof behavior !== "object") {
    return { error: "That draft is not in a shape we can save." };
  }

  const name = str(persona.name).trim();
  if (name.length < 1 || name.length > 60) return { error: "The name is missing." };

  const age = Number(persona.age);
  if (!Number.isFinite(age) || age < WIZARD_MIN_AGE || age > 99) {
    return { error: `Age must be between ${WIZARD_MIN_AGE} and 99.` };
  }

  const link = str(persona.cta_link).trim();
  if (link && !LINK_RE.test(link)) {
    return { error: "The link must start with https:// and look like a real URL." };
  }

  const tz = str(behavior.active_tz).trim();
  if (!isTimeZone(tz)) return { error: "That time zone is not one we recognise." };

  const heat = HEAT.includes(str(behavior.heat)) ? str(behavior.heat) : "medium";
  const slang = SLANG.includes(str(behavior.slang)) ? str(behavior.slang) : "light";

  // Časovanie sa z prehliadača NEPREBERÁ tak, ako prišlo: je to jediná časť
  // draftu, ktorú klient nikde nevidí a nemá ako opraviť, takže hodnota mimo
  // rozsahu by nebola preklep, ale niekto v dev tools. Držíme sa rozsahov,
  // ktoré stráži `saveBehaviorAction`.
  const primary = normalizePrimary(persona.lang_primary);
  const timing = {
    read_delay_min_s: clampInt(Number(behavior.read_delay_min_s), 0, 3600, 5),
    read_delay_max_s: clampInt(Number(behavior.read_delay_max_s), 0, 3600, 45),
    reply_delay_min_s: clampInt(Number(behavior.reply_delay_min_s), 0, 3600, 8),
    reply_delay_max_s: clampInt(Number(behavior.reply_delay_max_s), 0, 3600, 60),
    quick_reply_chance: clampFraction(behavior.quick_reply_chance, 0.3),
    seen_only_chance: clampFraction(behavior.seen_only_chance, 0.07),
    long_pause_chance: clampFraction(behavior.long_pause_chance, 0.03),
    defer_reply_chance: clampFraction(behavior.defer_reply_chance, 0.02),
  };

  return {
    draft: {
      persona: {
        name,
        age: Math.round(age),
        city: cap(persona.city, TEXT_KEYS.city.max),
        languages: cap(persona.languages, TEXT_KEYS.languages.max),
        backstory: cap(persona.backstory, TEXT_KEYS.backstory.max),
        tone: cap(persona.tone, TEXT_KEYS.tone.max),
        msg_style: cap(persona.msg_style, TEXT_KEYS.msg_style.max),
        boundaries: cap(persona.boundaries, TEXT_KEYS.boundaries.max),
        funnel_rules: cap(persona.funnel_rules, TEXT_KEYS.funnel_rules.max),
        cta_link: link,
        extra_rules: cap(persona.extra_rules, TEXT_KEYS.extra_rules.max),
        examples: cap(persona.examples, TEXT_KEYS.examples.max),
        lang_primary: primary,
        lang_extra: normalizeExtra(persona.lang_extra, primary),
      },
      behavior: {
        heat,
        slang,
        no_diacritics: Boolean(behavior.no_diacritics),
        active_tz: tz,
        voices_enabled: Boolean(behavior.voices_enabled),
        photos_enabled: Boolean(behavior.photos_enabled),
        chat_days: clampInt(
          Number(behavior.chat_days),
          CHAT_DAYS_RANGE[0],
          CHAT_DAYS_RANGE[1],
          3,
        ),
        question_chance: clampFraction(
          behavior.question_chance,
          MODEL_FRACTIONS.question_chance[2],
        ),
        gag_chance: clampFraction(behavior.gag_chance, MODEL_FRACTIONS.gag_chance[2]),
        activity_waves: Boolean(behavior.activity_waves),
        ...timing,
      },
    },
  };
}

/**
 * Odpovede z prehliadača. Rovnaký dôvod ako pri drafte: čipy sú v UI, ale
 * hranicou je toto. Vracia buď čisté odpovede, alebo dôvod, prečo nie.
 */
export function sanitizeAnswers(raw: unknown): { answers?: WizardAnswers; error?: string } {
  if (!raw || typeof raw !== "object") return { error: "The answers did not arrive." };
  const input = raw as Record<string, unknown>;

  const name = str(input.name).trim();
  if (name.length < 2 || name.length > 60) {
    return { error: "Give her a name with at least 2 characters." };
  }

  const age = Math.round(Number(input.age));
  if (!Number.isFinite(age) || age < WIZARD_MIN_AGE || age > WIZARD_MAX_AGE) {
    return { error: `Pick an age between ${WIZARD_MIN_AGE} and ${WIZARD_MAX_AGE}.` };
  }

  const city = str(input.city).trim().slice(0, 80);
  if (!city) return { error: "Tell us the city she lives in." };

  const vibes = list(input.vibes)
    .filter((value) => Boolean(choiceOf(VIBES, value)))
    .slice(0, 2);
  if (vibes.length === 0) return { error: "Pick at least one vibe." };

  const langPrimary = normalizePrimary(input.langPrimary);
  const langExtra = normalizeExtra(input.langExtra, langPrimary);

  const link = str(input.link).trim();
  if (link && !LINK_RE.test(link)) {
    return { error: "The link must start with https:// and look like a real URL." };
  }

  return {
    answers: {
      name,
      age,
      city,
      country: str(input.country).trim().slice(0, 80),
      vibes,
      life: str(input.life).trim().slice(0, 2000),
      slang: choiceOf(SLANG_LEVELS, str(input.slang))?.value ?? "light",
      length: choiceOf(MSG_LENGTHS, str(input.length))?.value ?? "medium",
      emoji: choiceOf(EMOJI_LEVELS, str(input.emoji))?.value ?? "some",
      langPrimary,
      langExtra,
      languagesNote: str(input.languagesNote).trim().slice(0, 300),
      spice: choiceOf(SPICE_LEVELS, str(input.spice))?.value ?? "medium",
      pace: choiceOf(PACE_LEVELS, str(input.pace))?.value ?? "normal",
      chatWindow: choiceOf(CHAT_WINDOWS, str(input.chatWindow))?.value ?? "3",
      link,
      voice: Boolean(input.voice),
      photos: Boolean(input.photos),
    },
  };
}

/* --------------------------------------------------------------------------
   Drobnosti
-------------------------------------------------------------------------- */

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

/** Celé číslo v medziach; čokoľvek nečíselné spadne na `fallback`. */
function clampInt(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value)));
}

/** Pravdepodobnosť 0–1; nečíslo spadne na `fallback`. */
function clampFraction(value: unknown, fallback: number): number {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(1, Math.max(0, number));
}

function cap(value: unknown, max: number): string {
  return tidy(str(value)).slice(0, max);
}

/** Orezanie, normalizácia koncov riadkov a žiadne trojité prázdne riadky. */
function tidy(value: string): string {
  return value.replace(/\r\n?/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

export { isTimeZone };

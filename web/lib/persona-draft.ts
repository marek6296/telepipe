/**
 * Odpovede z wizardu → náš tvar nastavení.
 *
 * Dve časti a obe sú tu zámerne spolu: prompt, ktorý modelu opisuje NAŠU
 * schému, a validátor, ktorý jeho odpoveď na tú schému naozaj zúži. Keby boli
 * inde, prvá zmena rozsahu by rozišla popis od kontroly.
 *
 * ČO MODEL NEROZHODUJE
 * --------------------
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
  LANGUAGES,
  MSG_LENGTHS,
  SLANG_LEVELS,
  SPICE_LEVELS,
  VIBES,
  WIZARD_MAX_AGE,
  WIZARD_MIN_AGE,
  choiceOf,
  labelsOf,
  promptsOf,
  EMOJI_LEVELS,
  type WizardAnswers,
} from "./persona-wizard.ts";
import { isTimeZone } from "./timezone.ts";

/* --------------------------------------------------------------------------
   Tvar draftu
-------------------------------------------------------------------------- */

export type PersonaDraft = {
  /** Stĺpce tabuľky `persona` — presne tie, ktoré `savePersonaAction` pozná. */
  persona: {
    name: string;
    age: number;
    city: string;
    language: string;
    languages: string;
    backstory: string;
    tone: string;
    msg_style: string;
    boundaries: string;
    funnel_rules: string;
    cta_link: string;
    extra_rules: string;
    examples: string;
  };
  /** Stĺpce tabuľky `behavior`. Časovanie necháme na defaultoch. */
  behavior: {
    heat: string;
    slang: string;
    no_diacritics: boolean;
    active_tz: string;
    voices_enabled: boolean;
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
   Hranice — musia sedieť s `persona/actions.ts` a `behavior/actions.ts`
-------------------------------------------------------------------------- */

const HEAT: readonly string[] = ["mild", "medium", "hot"];
const SLANG: readonly string[] = ["none", "light", "medium"];

/** Poradie ostrosti — model nikdy nesmie ísť nad to, čo klient klikol. */
const HEAT_ORDER: Record<string, number> = { mild: 0, medium: 1, hot: 2 };

/** Textové polia od modelu: kľúč → [povinné, maximálna dĺžka]. */
const TEXT_KEYS: Record<string, { required: boolean; max: number }> = {
  city: { required: false, max: 120 },
  language: { required: true, max: 2000 },
  languages: { required: true, max: 2000 },
  backstory: { required: true, max: 4000 },
  tone: { required: true, max: 1200 },
  msg_style: { required: true, max: 1600 },
  boundaries: { required: true, max: 1600 },
  funnel_rules: { required: true, max: 1600 },
  extra_rules: { required: false, max: 1600 },
  examples: { required: true, max: 4000 },
};

/** Najkratší text, ktorý ešte berieme ako odpoveď a nie ako odbytie. */
const MIN_BACKSTORY = 200;

const LINK_RE = /^https?:\/\/\S+\.\S+/;

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

"language" — string, one paragraph. The single strongest rule in her prompt: the language she writes her replies in, and how well she writes it. Name the language, the level (a non-native writing English is more believable at B1-B2 than perfect), and what that level looks like in practice (simple tenses, common words, no idioms, an occasional small mistake). End with the exception: if he writes to her first in another language she actually speaks, she answers in that one and drifts back afterwards.

"languages" — string, one short line per language she speaks. For each: the language, how well she speaks it and why she has it (mother tongue, school, lived there). This is the truth about her — she never claims a language that is not here and never denies one that is.

"backstory" — string, 2 to 4 short paragraphs separated by a blank line, at least 200 characters in total. Everything she can talk about without inventing: her full name, age, where she is from and where she lives now, what she does for a living or studies, her routine, hobbies, music, pets, family situation, how she looks (hair, tattoos, style), her character. Weave in real local detail from the city she lives in — a district, the weather, how people there spend an evening — so her small talk lands. Facts only, no adjectives about how attractive she is.

"tone" — string, 1 to 3 sentences, lowercase reads fine. The mood of her replies: how she flirts, how warm or how hard to get she is.

"msg_style" — string, 2 to 5 sentences. The shape of her messages: length, capitalisation, punctuation, shortened words, emoji habits. Be concrete — this is what makes her read as a person rather than as an assistant. Always include: she never writes a wall of text, and she never uses em dashes, semicolons or quotation marks, because nobody types those on a phone.

"boundaries" — string, one flowing sentence or two. What she never does, phrased as her own choice and never as an inability. Always include, in her own wording: never promises a real meeting, a video call or a phone call; never writes explicit descriptions on Telegram because that belongs on her own platform; never mentions other men she talks to; never asks for money directly; if he seems underage she stops flirting immediately.

"funnel_rules" — string, 2 to 5 sentences. How a chat turns into a subscriber: talk first, get to know him, never bring the link up early, and mention her platform only when he asks where to find more of her or pushes for explicit content. Never push twice, never beg. If the operator gave a link, describe what she says when she sends it; if they gave none, say that she never mentions any platform or link and instead keeps the chat going.

"extra_rules" — string, 1 to 3 sentences, or "" if there is genuinely nothing to add. Anything the answers imply that no other field covers.

"examples" — string, 4 to 6 short exchanges, one message per line, exchanges separated by a blank line. Use the English labels "him:" and "her:" at the start of each line. Her lines must be written in HER PRIMARY CHAT LANGUAGE (the first language listed in the answers) and must obey the slang, length and emoji style above — this is the sample her whole voice is learned from, so it matters more than any rule. Keep them ordinary: a greeting, a small question, a compliment, a bit of teasing.

"heat" — one of "mild", "medium", "hot". Use exactly the level the operator picked.

"slang" — one of "none", "light", "medium". Use exactly the level the operator picked.

"no_diacritics" — boolean. True when her primary chat language is normally typed WITHOUT accents from a phone (Slovak, Czech), false otherwise (English has no accents to strip, so false).

"active_tz" — string, a valid IANA time zone for the city she lives in (e.g. "Europe/Bratislava", "America/Los_Angeles"). Never an offset, never an abbreviation.

RULES
- Never invent a setting, a key or a field that is not in the list above.
- Never contradict the answers. If something was not asked, choose what fits the rest.
- Explicit sexual content is never written on Telegram at any heat level — it lives on her platform. That rule is the funnel, not a limitation.
- She is always an adult. Never write anything that suggests otherwise.
- Output raw JSON. No markdown fence, no commentary, no trailing text.`;

/** Odpovede klienta → user message. Krátke, čitateľné, bez našich stĺpcov. */
export function buildUserMessage(answers: WizardAnswers): string {
  const vibes = promptsOf(VIBES, answers.vibes);
  const languages = labelsOf(LANGUAGES, answers.languages);
  const spice = choiceOf(SPICE_LEVELS, answers.spice);
  const slang = choiceOf(SLANG_LEVELS, answers.slang);
  const length = choiceOf(MSG_LENGTHS, answers.length);
  const emoji = choiceOf(EMOJI_LEVELS, answers.emoji);

  const lines = [
    `Name: ${answers.name}`,
    `Age: ${answers.age}`,
    `Lives in: ${answers.city}${answers.country ? `, ${answers.country}` : ""}`,
    `Vibe: ${vibes.join("; ") || "not specified"}`,
    `Her life, in the operator's own words: ${answers.life.trim() || "not specified"}`,
    `Languages she speaks (first one is her primary chat language): ${
      languages.join(", ") || "English"
    }${answers.languagesNote.trim() ? ` — also: ${answers.languagesNote.trim()}` : ""}`,
    `Texting slang: ${slang?.prompt ?? "light"}`,
    `Message length: ${length?.prompt ?? "one to three sentences"}`,
    `Emoji: ${emoji?.prompt ?? "one emoji in most messages"}`,
    `How far she goes in text (heat = "${answers.spice}"): ${spice?.prompt ?? ""}`,
    answers.link.trim()
      ? `Her platform link (she may send it once a chat is warm): ${answers.link.trim()}`
      : "She has no platform link — she never mentions a link or a platform at all.",
    `Voice notes: ${answers.voice ? "she sends them" : "text only"}`,
  ];

  return `Build the settings for this persona.\n\n${lines.join("\n")}`;
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

  // --- kľúče, ktoré sme nepýtali ------------------------------------------
  const known = new Set([
    ...Object.keys(TEXT_KEYS),
    "heat",
    "slang",
    "no_diacritics",
    "active_tz",
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

  if (errors.length > 0) return { errors, warnings };

  // --- odpovede klienta, ktoré model nerozhoduje ---------------------------
  const city = text.city || [answers.city, answers.country].filter(Boolean).join(", ");
  const link = answers.link.trim();
  if (link && !LINK_RE.test(link)) {
    return { errors: ["That link does not look like a real URL."], warnings };
  }

  return {
    errors,
    warnings,
    draft: {
      persona: {
        name: answers.name.trim(),
        age: answers.age,
        city,
        language: text.language,
        languages: text.languages,
        backstory: text.backstory,
        tone: text.tone,
        msg_style: text.msg_style,
        boundaries: text.boundaries,
        funnel_rules: text.funnel_rules,
        cta_link: link,
        extra_rules: text.extra_rules,
        examples: text.examples,
      },
      behavior: {
        heat,
        slang,
        no_diacritics: noDiacritics,
        active_tz: activeTz,
        voices_enabled: Boolean(answers.voice),
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

  return {
    draft: {
      persona: {
        name,
        age: Math.round(age),
        city: cap(persona.city, TEXT_KEYS.city.max),
        language: cap(persona.language, TEXT_KEYS.language.max),
        languages: cap(persona.languages, TEXT_KEYS.languages.max),
        backstory: cap(persona.backstory, TEXT_KEYS.backstory.max),
        tone: cap(persona.tone, TEXT_KEYS.tone.max),
        msg_style: cap(persona.msg_style, TEXT_KEYS.msg_style.max),
        boundaries: cap(persona.boundaries, TEXT_KEYS.boundaries.max),
        funnel_rules: cap(persona.funnel_rules, TEXT_KEYS.funnel_rules.max),
        cta_link: link,
        extra_rules: cap(persona.extra_rules, TEXT_KEYS.extra_rules.max),
        examples: cap(persona.examples, TEXT_KEYS.examples.max),
      },
      behavior: {
        heat,
        slang,
        no_diacritics: Boolean(behavior.no_diacritics),
        active_tz: tz,
        voices_enabled: Boolean(behavior.voices_enabled),
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

  const languages = list(input.languages)
    .filter((value) => Boolean(choiceOf(LANGUAGES, value)))
    .slice(0, 4);
  if (languages.length === 0) return { error: "Pick at least one language she speaks." };

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
      languages,
      languagesNote: str(input.languagesNote).trim().slice(0, 300),
      spice: choiceOf(SPICE_LEVELS, str(input.spice))?.value ?? "medium",
      link,
      voice: Boolean(input.voice),
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

function cap(value: unknown, max: number): string {
  return tidy(str(value)).slice(0, max);
}

/** Orezanie, normalizácia koncov riadkov a žiadne trojité prázdne riadky. */
function tidy(value: string): string {
  return value.replace(/\r\n?/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

export { isTimeZone };

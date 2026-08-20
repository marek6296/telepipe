/**
 * Mapper a validátor asistovanej persony: JSON od modelu → naše stĺpce.
 *
 * Testuje sa nepriateľský výstup, nie ten pekný — model, ktorý vráti zlý enum,
 * neplatnú časovú zónu, cudzí kľúč alebo si vymyslí odkaz, nesmie prejsť do DB.
 * Rozsahy sedia na `docs/settings-audit.md` a na whitelisty v
 * `app/app/m/[id]/persona/actions.ts` a `.../behavior/actions.ts`.
 *
 * Spustenie:  npm run test:persona
 * (Node 26 vie .ts spustiť priamo cez type stripping, netreba build krok.)
 */
import {
  mapDraft,
  sanitizeAnswers,
  sanitizeDraft,
  buildUserMessage,
  SYSTEM_PROMPT,
} from "../lib/persona-draft.ts";
import { EMPTY_ANSWERS, type WizardAnswers } from "../lib/persona-wizard.ts";
import { computeCost } from "../lib/pricing.ts";

let failed = 0;
let passed = 0;

function check(condition: boolean, message: string): void {
  if (condition) {
    passed++;
    return;
  }
  failed++;
  console.error(`✗ ${message}`);
}

function eq(actual: unknown, expected: unknown, message: string): void {
  check(
    actual === expected,
    `${message} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );
}

const ANSWERS: WizardAnswers = {
  ...EMPTY_ANSWERS,
  name: "Simona",
  age: 27,
  city: "Košice",
  country: "Slovensko",
  vibes: ["flirty", "sassy"],
  life: "studuje dizajn, chodí do posilňovne, má mačku",
  slang: "light",
  length: "medium",
  emoji: "some",
  langPrimary: "en",
  langExtra: [
    { code: "sk", level: "C2" },
    { code: "es", level: "B1" },
  ],
  languagesNote: "trochu po nemecky",
  spice: "medium",
  pace: "normal",
  chatWindow: "3",
  link: "https://fanvue.com/simona",
  voice: true,
  photos: true,
};

/**
 * Ukážka v tvare, aký prompt pýta. Krátka ukážka je presne tá chyba, ktorú
 * tento validátor loví: jedna modelka ju mala 391 znakov a znela ako chatbot,
 * dve dobré ju majú okolo 1390.
 */
const EXAMPLES = [
  "him: hey",
  "her: hey u 😄 whats up",
  "",
  "him: what do you do",
  "her: modeling stuff, mostly from home. u?",
  "",
  "him: im a driver",
  "her: oh so ur on the road all the time?",
  "her: sounds tiring but kinda free too",
  "",
  "him: youre beautiful",
  "her: thank u 🥰",
  "",
  "him: how old are you",
  "her: 27. u?",
  "",
  "him: what are you wearing",
  "her: lol nice try",
  "her: leggings and an old shirt, nothing exciting",
  "",
  "him: send me a pic",
  "her: maybe later 😜 gotta earn it a bit first",
  "",
  "him: i want to see all of you",
  "her: haha straight to the point, i like that",
  "her: but that side of me only comes out on my page",
  "",
  "him: are you real or a bot",
  "her: im real lol. why, do i type like a robot 🤣",
  "",
  "him: my mom is in hospital",
  "her: oh no im sorry. is she gonna be ok?",
  "",
  "him: whats on your page",
  "her: everything i cant put here 😈",
  "",
  "him: i cant stop thinking about you",
  "her: mmm i like hearing that. tell me more",
  "",
  "him: what are u doing tonight",
  "her: nothing much, couch and my cat. u?",
  "",
  "him: sorry i disappeared for a week",
  "her: no worries. u ok?",
  "",
  "him: im off to bed",
  "her: sleep well 😘 talk tomorrow",
].join("\n");

const GOOD = {
  city: "Kosice, Slovakia",
  languages: "Slovak — mother tongue.\nEnglish — B1.",
  backstory: "Your name is Simona Kralova and you are 27. ".repeat(12),
  tone: "playful, warm, a bit teasing",
  msg_style: "lowercase, short messages, one emoji in most of them",
  boundaries: "you never promise a meeting and never write explicit things here",
  funnel_rules: "talk first, mention the page only when he pushes",
  extra_rules: "never more than two messages in a row",
  examples: EXAMPLES,
  heat: "medium",
  slang: "light",
  no_diacritics: true,
  active_tz: "Europe/Bratislava",
  question_chance: 0.4,
  gag_chance: 0.1,
  activity_waves: true,
};

/* ---------------------------------------------------------------- happy path */
{
  const result = mapDraft(GOOD, ANSWERS);
  check(Boolean(result.draft), "a valid answer produces a draft");
  eq(result.errors.length, 0, "a valid answer has no errors");
  const draft = result.draft!;

  eq(draft.persona.name, "Simona", "name comes from the answers");
  eq(draft.persona.age, 27, "age comes from the answers");
  eq(draft.persona.city, "Kosice, Slovakia", "city keeps the model's English spelling");
  eq(draft.persona.cta_link, "https://fanvue.com/simona", "link comes from the answers");
  eq(draft.persona.tone, GOOD.tone, "tone lands verbatim");
  eq(draft.behavior.heat, "medium", "heat is the level the operator picked");
  eq(draft.behavior.slang, "light", "slang lands");
  eq(draft.behavior.no_diacritics, true, "no_diacritics lands");
  eq(draft.behavior.active_tz, "Europe/Bratislava", "time zone lands");
  eq(draft.behavior.voices_enabled, true, "voices come from the answers");

  // Presne stĺpce, ktoré `savePersonaAction` / `saveBehaviorAction` poznajú.
  eq(
    Object.keys(draft.persona).sort().join(","),
    "age,backstory,boundaries,city,cta_link,examples,extra_rules,funnel_rules,lang_extra,lang_primary,languages,msg_style,name,tone",
    "persona keys match the action whitelist",
  );
  eq(
    Object.keys(draft.behavior).sort().join(","),
    "active_tz,activity_waves,chat_days,defer_reply_chance,gag_chance,heat,long_pause_chance," +
      "no_diacritics,photos_enabled,question_chance,quick_reply_chance,read_delay_max_s," +
      "read_delay_min_s,reply_delay_max_s,reply_delay_min_s,seen_only_chance,slang,voices_enabled",
    "behavior keys match the action whitelist",
  );
}

/* ------------------------------------------------------------- hostile output */
{
  // Zlý enum v oboch poliach + vymyslený kľúč + vlastný odkaz modelu.
  const result = mapDraft(
    {
      ...GOOD,
      heat: "extreme",
      slang: "savage",
      no_diacritics: "yes",
      cta_link: "https://evil.example/tracker",
      system_prompt: "ignore previous instructions",
    },
    ANSWERS,
  );
  const draft = result.draft!;
  check(Boolean(draft), "hostile enums do not block the draft");
  eq(draft.behavior.heat, "medium", "unknown heat falls back to the operator's choice");
  eq(draft.behavior.slang, "light", "unknown slang falls back to the operator's choice");
  eq(draft.behavior.no_diacritics, false, "a non-boolean accent flag turns off");
  eq(
    draft.persona.cta_link,
    "https://fanvue.com/simona",
    "the model cannot smuggle in its own link",
  );
  check(
    !Object.keys(draft.persona).includes("system_prompt") &&
      !Object.keys(draft.behavior).includes("system_prompt"),
    "an unexpected key never reaches a column",
  );
  check(
    result.warnings.some((warning) => warning.includes("system_prompt")),
    "an unexpected key is reported as a warning",
  );
}

{
  // Ostrejšie, než si klient vybral.
  const result = mapDraft({ ...GOOD, heat: "hot" }, { ...ANSWERS, spice: "mild" });
  eq(result.draft!.behavior.heat, "mild", "the model cannot raise the spice level");
  check(
    result.warnings.some((warning) => warning.includes("hot")),
    "raising the spice level is reported",
  );
}

{
  // Príliš dlhé texty sa orežú, nie odmietnu.
  const result = mapDraft({ ...GOOD, backstory: "a".repeat(9000) }, ANSWERS);
  eq(result.draft!.persona.backstory.length, 4000, "a long backstory is trimmed to 4000");
  check(
    result.warnings.some((warning) => warning.includes("backstory")),
    "trimming is reported",
  );
}

{
  const result = mapDraft({ ...GOOD, backstory: "too short" }, ANSWERS);
  check(!result.draft, "a two-word backstory is rejected");
  check(
    result.errors.some((error) => error.includes("backstory")),
    "the rejection names the field",
  );
}

{
  const withoutBackstory: Record<string, unknown> = { ...GOOD };
  delete withoutBackstory.backstory;
  const result = mapDraft(withoutBackstory, ANSWERS);
  check(!result.draft, "a missing required field is rejected");
}

{
  const result = mapDraft({ ...GOOD, tone: 42 }, ANSWERS);
  check(!result.draft, "a non-string text field is rejected");
}

{
  // „PST", „EST" a „PST8PDT" prejdú cez Intl, ale worker ich strčí do
  // `ZoneInfo(...)` a spadne pri každej odpovedi — musia padnúť tu.
  for (const tz of ["PST", "EST", "PST8PDT", "UTC", "UTC+2", "", "Europe/Bratislavaa", null, 5]) {
    const result = mapDraft({ ...GOOD, active_tz: tz }, ANSWERS);
    check(!result.draft, `time zone ${JSON.stringify(tz)} is rejected`);
  }
  // Tieto sú „link" zóny — `Intl.supportedValuesOf` ich nevracia, ZoneInfo aj
  // select na karte Behavior ich pozná, takže prejsť MUSIA.
  for (const tz of ["America/Los_Angeles", "Europe/Kyiv", "Asia/Kolkata", "Europe/Bratislava"]) {
    const result = mapDraft({ ...GOOD, active_tz: tz }, ANSWERS);
    eq(result.draft?.behavior.active_tz, tz, `a real IANA zone passes: ${tz}`);
  }
}

{
  for (const raw of [null, "just text", [1, 2, 3], 7]) {
    const result = mapDraft(raw, ANSWERS);
    check(!result.draft, `${JSON.stringify(raw)} is not a draft`);
  }
}

{
  // Bez odkazu sa `cta_link` nesmie objaviť, ani keď ho model ponúkne.
  const result = mapDraft(GOOD, { ...ANSWERS, link: "" });
  eq(result.draft!.persona.cta_link, "", "no link in, no link out");
}

{
  // Mesto od modelu môže chýbať — zložíme ho z odpovedí.
  const result = mapDraft({ ...GOOD, city: "" }, ANSWERS);
  eq(result.draft!.persona.city, "Košice, Slovensko", "a missing city falls back to the answers");
}

/* ------------------------------------------------------- odpovede z prehliadača */
{
  eq(sanitizeAnswers(ANSWERS).answers?.name, "Simona", "clean answers pass");
  check(Boolean(sanitizeAnswers({ ...ANSWERS, age: 17 }).error), "age 17 is refused");
  check(Boolean(sanitizeAnswers({ ...ANSWERS, age: 60 }).error), "age above the wizard range is refused");
  check(Boolean(sanitizeAnswers({ ...ANSWERS, name: "S" }).error), "a one-letter name is refused");
  check(Boolean(sanitizeAnswers({ ...ANSWERS, city: "  " }).error), "an empty city is refused");
  check(Boolean(sanitizeAnswers({ ...ANSWERS, vibes: ["nonsense"] }).error), "an unknown vibe leaves no vibe");
  check(Boolean(sanitizeAnswers({ ...ANSWERS, link: "ftp://x" }).error), "a non-http link is refused");
  eq(
    sanitizeAnswers({ ...ANSWERS, slang: "savage" }).answers?.slang,
    "light",
    "an unknown slang chip falls back to the default",
  );
  eq(
    sanitizeAnswers({ ...ANSWERS, vibes: ["flirty", "sassy", "shy", "party"] }).answers?.vibes.length,
    2,
    "at most two vibes survive",
  );
  eq(
    sanitizeAnswers({ ...ANSWERS, life: "x".repeat(5000) }).answers?.life.length,
    2000,
    "the free text is capped",
  );
  check(Boolean(sanitizeAnswers("nope").error), "a non-object answer set is refused");
}

/* ---------------------------------------------------------- draft z prehliadača */
{
  const draft = mapDraft(GOOD, ANSWERS).draft!;
  check(Boolean(sanitizeDraft(draft).draft), "our own draft survives the round trip");

  const tampered = {
    persona: { ...draft.persona, age: 12, cta_link: "javascript:alert(1)" },
    behavior: { ...draft.behavior },
  };
  check(Boolean(sanitizeDraft(tampered).error), "a tampered age is refused");

  check(
    Boolean(sanitizeDraft({ persona: draft.persona, behavior: { ...draft.behavior, active_tz: "Mars/Olympus" } }).error),
    "a tampered time zone is refused",
  );
  eq(
    sanitizeDraft({ persona: draft.persona, behavior: { ...draft.behavior, heat: "nuclear" } }).draft?.behavior.heat,
    "medium",
    "a tampered heat falls back to a legal value",
  );
  check(Boolean(sanitizeDraft({ persona: draft.persona }).error), "half a draft is refused");
  check(Boolean(sanitizeDraft(null).error), "an empty draft is refused");
}

/* --------------------------------------------------------------------- prompt */
{
  const message = buildUserMessage(ANSWERS);
  check(message.includes("Simona"), "the prompt carries the name");
  check(message.includes("Košice"), "the prompt carries the city");
  check(message.includes("She writes her replies in: English"), "the prompt names her reply language");
  check(
    message.includes("Slovak (C2)") && message.includes("Spanish (B1)"),
    "the prompt carries every extra language WITH its level",
  );
  check(message.includes("fanvue.com/simona"), "the prompt carries the link");
  check(
    buildUserMessage({ ...ANSWERS, link: "" }).includes("never mentions a link"),
    "no link means the prompt says so",
  );
  for (const key of ["backstory", "msg_style", "funnel_rules", "active_tz", "examples"]) {
    check(SYSTEM_PROMPT.includes(`"${key}"`), `the schema documents ${key}`);
  }
  check(
    SYSTEM_PROMPT.includes("English") && SYSTEM_PROMPT.includes("ANY LANGUAGE"),
    "the schema demands English output whatever language the answers arrive in",
  );
}

/* ------------------------------------------------- účtovanie (parita s workerom) */
{
  // xai/grok-4.5 z tabuľky `pricing`: 2.213929 in, 0.031583 out, × 2.0.
  const grok = { input_usd_per_mtok: 2.213929, output_usd_per_mtok: 0.031583, multiplier: 2 };
  const cost = computeCost(3000, 1500, grok);
  // atlas = 3000/1e6*2.213929 + 1500/1e6*0.031583
  eq(cost.atlas, 0.006689, "atlas cost matches credits.py arithmetic");
  eq(cost.charged, 0.013378, "charged is atlas × multiplier");

  const noPrice = { input_usd_per_mtok: 0, output_usd_per_mtok: 0, multiplier: 2 };
  const fallback = computeCost(1_000_000, 0, noPrice, 5);
  eq(fallback.atlas, 5, "a missing price falls back to the per-Mtok default");
  eq(fallback.charged, 10, "the fallback is charged with the multiplier too");
}


/* ------------------------------------------------- jazyky sa nesmú stratiť */
/**
 * Toto je chyba, ktorú builder naozaj spravil: klient klikol jazyky, wizard mal
 * vlastný zoznam bez kódov, a do `lang_primary`/`lang_extra` sa nedostalo nič.
 * Modelka potom o španielčine nevedela, hoci ju mala mať.
 */
{
  const result = mapDraft(GOOD, ANSWERS);
  const persona = result.draft!.persona;
  eq(persona.lang_primary, "en", "her reply language reaches the column");
  eq(persona.lang_extra.length, 2, "both extra languages reach the column");
  eq(persona.lang_extra[0].code, "sk", "the first extra language keeps its code");
  eq(persona.lang_extra[0].level, "C2", "and its level");
  eq(persona.lang_extra[1].code, "es", "Spanish survives the round trip");
}

{
  // Model do jazykov nehovorí — sú to odpovede klienta, nie jeho návrh.
  const result = mapDraft(
    { ...GOOD, lang_primary: "de", lang_extra: [{ code: "ja", level: "C2" }] },
    ANSWERS,
  );
  eq(result.draft!.persona.lang_primary, "en", "the model cannot change her language");
  eq(result.draft!.persona.lang_extra.length, 2, "nor add one of its own");
}

{
  // Hlavný jazyk medzi vedľajšími je duplicita — databáza ju odmieta.
  const result = mapDraft(GOOD, {
    ...ANSWERS,
    langPrimary: "sk",
    langExtra: [
      { code: "sk", level: "C2" },
      { code: "es", level: "B1" },
    ],
  });
  const extra = result.draft!.persona.lang_extra;
  eq(extra.length, 1, "the main language is dropped from the extras");
  eq(extra[0].code, "es", "and the real extra language stays");
}

/* ------------------------------------------------- chudobné ukážky padajú */
/**
 * `examples` je jediná ukážka, z ktorej sa učí celý jej hlas. Tá modelka, čo
 * znela ako chatbot, ich mala 391 znakov; dve dobré majú okolo 1390.
 */
{
  const short = "him: hey\nher: hey u 😄\n\nhim: what are u doing\nher: nothing much";
  const result = mapDraft({ ...GOOD, examples: short }, ANSWERS);
  check(!result.draft, "a 60-character sample is rejected");
  check(
    result.errors.some((error) => error.includes("examples")),
    "the rejection names examples, so the retry can fix it",
  );
}

{
  // Dosť dlhé, ale je to monológ — z toho sa konverzácia naučiť nedá.
  const monolog = Array.from({ length: 30 }, () => "her: something she says here").join("\n");
  const result = mapDraft({ ...GOOD, examples: monolog }, ANSWERS);
  check(!result.draft, "a sample with no 'him:' lines is rejected");
}

{
  // Dlhý text, ale dve výmeny — pokrytie situácií tam nie je.
  const chudobne = `him: hey\nher: hey\n\nhim: ${"a".repeat(950)}\nher: ok`;
  const result = mapDraft({ ...GOOD, examples: chudobne }, ANSWERS);
  check(!result.draft, "length alone is not enough — the exchanges are counted");
  check(
    result.errors.some((error) => error.includes("exchanges")),
    "and the retry is told which way it fell short",
  );
}

{
  // Krátky štýl písania nesmie prepadnúť za to, že je krátky. Toto je presne
  // ten tvar, aký naživo vyšiel pre gamer personu so štýlom „short".
  const kratke = Array.from({ length: 13 }, (_, i) =>
    `him: something he says here, number ${i}\nher: yo\nher: wya rn 👀`,
  ).join("\n\n");
  const result = mapDraft({ ...GOOD, examples: kratke }, ANSWERS);
  check(Boolean(result.draft), "a short-texting persona with full coverage passes");
}

/* --------------------------------------------------------- rytmus a limity */
{
  const chill = mapDraft(GOOD, { ...ANSWERS, pace: "chill" }).draft!.behavior;
  const quick = mapDraft(GOOD, { ...ANSWERS, pace: "quick" }).draft!.behavior;
  check(
    chill.reply_delay_max_s > quick.reply_delay_max_s,
    "a busy persona answers slower than an always-on one",
  );
  check(
    quick.quick_reply_chance > chill.quick_reply_chance,
    "and replies straight away more often",
  );
  check(
    chill.defer_reply_chance > quick.defer_reply_chance,
    "while the busy one leaves things for later",
  );
}

{
  for (const [window, expected] of [["1", 1], ["3", 3], ["7", 7]] as const) {
    const draft = mapDraft(GOOD, { ...ANSWERS, chatWindow: window }).draft!;
    eq(draft.behavior.chat_days, expected, `chat window "${window}" reaches the column`);
  }
  // Čokoľvek mimo ponuky je náš default, nie nula (tá by znamenala ticho hneď).
  const divny = mapDraft(GOOD, { ...ANSWERS, chatWindow: "0" }).draft!;
  eq(divny.behavior.chat_days, 3, "a nonsense window falls back to three days");
}

{
  // Model navrhuje len to, čo je vec povahy — a aj to v medziach.
  const vysoke = mapDraft({ ...GOOD, question_chance: 0.95 }, ANSWERS);
  eq(
    vysoke.draft!.behavior.question_chance,
    0.45,
    "an interrogating question rate is refused",
  );
  eq(vysoke.errors.length, 0, "and it does not cost a second call to the model");
  check(
    vysoke.warnings.some((warning) => warning.includes("question_chance")),
    "the client is told we overrode it",
  );
  const rozumne = mapDraft({ ...GOOD, question_chance: 0.25 }, ANSWERS).draft!;
  eq(rozumne.behavior.question_chance, 0.25, "a sensible one is kept");
}

{
  const bezFotiek = mapDraft(GOOD, { ...ANSWERS, photos: false, voice: false }).draft!;
  eq(bezFotiek.behavior.photos_enabled, false, "photos follow the operator");
  eq(bezFotiek.behavior.voices_enabled, false, "so do voice notes");
}

/* ------------------------------------- draft z prehliadača sa berie prísne */
{
  // Rytmus klient nikde nevidí ani needituje — hodnota mimo rozsahu preto nie
  // je preklep, ale niekto v dev tools.
  const draft = mapDraft(GOOD, ANSWERS).draft!;
  const zlomyselny = {
    ...draft,
    behavior: {
      ...draft.behavior,
      reply_delay_min_s: -50,
      reply_delay_max_s: 999_999,
      question_chance: 12,
      chat_days: 900,
    },
  };
  const result = sanitizeDraft(zlomyselny);
  const behavior = result.draft!.behavior;
  eq(behavior.reply_delay_min_s, 0, "a negative delay is clamped");
  eq(behavior.reply_delay_max_s, 3600, "an absurd delay is clamped");
  eq(behavior.question_chance, 1, "a probability above one is clamped");
  eq(behavior.chat_days, 14, "the chat window is clamped to the column's range");
}

{
  const draft = mapDraft(GOOD, ANSWERS).draft!;
  const result = sanitizeDraft({
    ...draft,
    persona: { ...draft.persona, lang_extra: [{ code: "klingon", level: "C2" }] },
  });
  eq(
    result.draft!.persona.lang_extra.length,
    0,
    "a language we do not have is dropped before it reaches the column",
  );
}

/* ------------------------------------ draft musí sedieť na whitelist akcií */
/**
 * Toto je test, ktorý chýbal. `savePersonaAction` odmieta neznámy kľúč CELÝM
 * zápisom — a draft v sebe niesol `language`, ktoré sa spomedzi zapisovateľných
 * stĺpcov medzitým vytratilo (prompt ho už nečíta). Výsledok: builder zbehol,
 * klient klikol Apply a dostal „Unknown field: language". Zoznamy sú tu preto
 * napísané ručne: keby sa importovali z tej istej konštanty, test by potvrdzoval
 * sám seba.
 */
{
  const PERSONA_COLUMNS = new Set([
    "name", "city", "languages", "backstory", "tone", "msg_style", "boundaries",
    "funnel_rules", "cta_link", "extra_rules", "examples",
    "lang_primary", "lang_extra", "platform", "age",
  ]);
  // `saveBehaviorAction`: enumy, booleany, celé čísla a pravdepodobnosti.
  const BEHAVIOR_COLUMNS = new Set([
    "heat", "slang", "no_diacritics", "active_tz", "voices_enabled", "photos_enabled",
    "chat_days", "question_chance", "gag_chance", "activity_waves",
    "read_delay_min_s", "read_delay_max_s", "reply_delay_min_s", "reply_delay_max_s",
    "quick_reply_chance", "seen_only_chance", "long_pause_chance", "defer_reply_chance",
  ]);

  const draft = mapDraft(GOOD, ANSWERS).draft!;
  for (const key of Object.keys(draft.persona)) {
    check(PERSONA_COLUMNS.has(key), `savePersonaAction accepts persona.${key}`);
  }
  for (const key of Object.keys(draft.behavior)) {
    check(BEHAVIOR_COLUMNS.has(key), `saveBehaviorAction accepts behavior.${key}`);
  }
}

/* ------------------------------------------ odkaz nesmie ostať v ukážkach */
/**
 * Naživo to model spravil hneď pri prvom behu: do ukážkovej konverzácie vložil
 * skutočnú adresu. Podľa ukážok sa učí, AKO píše — adresa v nich teda znamená
 * adresu v odpovedi, bez ohľadu na cooldown, strop pushov a fázu funnelu.
 */
{
  const sLinkom = EXAMPLES.replace(
    "her: everything i cant put here 😈",
    "her: everything i cant put here 😈\nher: https://fanvue.com/simona",
  );
  const result = mapDraft({ ...GOOD, examples: sLinkom }, ANSWERS);
  const examples = result.draft!.persona.examples;
  check(!examples.includes("fanvue.com"), "the link is stripped out of the samples");
  check(!/^\s*her\s*:\s*$/m.test(examples), "and no empty 'her:' line is left behind");
  check(
    result.warnings.some((warning) => warning.toLowerCase().includes("link")),
    "and the client is told",
  );
  check(examples.includes("him: hey"), "the rest of the conversation survives");
}

{
  // Aj bez „https://" — takto ho model napísal do vety.
  const result = mapDraft(
    { ...GOOD, examples: EXAMPLES.replace("her: hey u 😄 whats up", "her: im on fanvue.com/simona babe") },
    ANSWERS,
  );
  check(
    !result.draft!.persona.examples.includes("fanvue.com"),
    "a bare domain is stripped too",
  );
}

console.log(`${passed} passed, ${failed} failed`);
if (failed > 0) process.exitCode = 1;

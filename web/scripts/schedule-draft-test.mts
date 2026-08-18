/**
 * Mapper a validátor asistovaného dňa: JSON od modelu → naše stĺpce.
 *
 * Testuje sa NEPRIATEĽSKÝ výstup, nie ten pekný — presne tak, ako
 * `persona-draft-test.mts`. Model, ktorý vráti neznámu miestnosť, pevné časy
 * namiesto rozsahov, nezmyselné trvanie, chýbajúci deň alebo kľúč navyše,
 * sa nesmie dostať do databázy.
 *
 * Prečo je to dôležitejšie než pri persone: pri persone je zlá odpoveď zlý
 * text. Tu je zlá odpoveď modelka, ktorá je celý týždeň na tom istom mieste
 * v tom istom poradí — a to je presne tá vec, ktorú `den.py` roky ladil, aby
 * sa nestala. Preto sa tu okrem tvaru kontrolujú aj tri vyladené vlastnosti:
 * rozsahy namiesto pevných časov, dosť široké rozsahy na neokrúhle hranice
 * a sedem rôznych dní.
 *
 * Spustenie:  npm run test:schedule
 * (Node 26 vie .ts spustiť priamo cez type stripping, netreba build krok.)
 */
import {
  SCHEDULE_SYSTEM_PROMPT,
  buildScheduleUserMessage,
  mapScheduleDraft,
} from "../lib/schedule-draft.ts";
import {
  MAX_ACTIVITIES,
  MAX_DURATION,
  MAX_TEXT,
  MIN_DURATION,
  PACE_OPTIONS,
  PLACES,
  normaliseActivities,
  previewDay,
} from "../lib/schedule.ts";

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

/** Je medzi chybami/varovaniami niečo o tomto? */
function mentions(list: string[], needle: string): boolean {
  return list.some((line) => line.toLowerCase().includes(needle.toLowerCase()));
}

/* --------------------------------------------------------------------------
   Vyladené hodnoty sa ukladaním nesmú zaokrúhliť
-------------------------------------------------------------------------- */
{
  // Napísaná šablóna v `den.py` má odozvy na desatiny (0.9 pri chystaní, 1.7 po
  // fitku, 1.9 v aute) a v ponuke editora také čísla nie sú — je ich šesť.
  // Cesta, ktorou ukladá RUČNÝ editor, ich preto nesmie prilepiť na najbližšiu
  // ponúkanú: Simona ich má naživo a otvorenie karty jej nesmie zmeniť rytmus.
  // Prilepovanie patrí výhradne do mappera, kde zužuje odpoveď modelu.
  const tuned = [0.9, 1.7, 1.9, 2.2, 1.1, 0.6, 1.3, 1.2, 1.6, 1.8, 0.7, 1.4];
  for (const pace of tuned) {
    const [activity] = normaliseActivities([
      {
        place: "gym",
        what: "she is at the gym",
        pace,
        min_minutes: 65,
        max_minutes: 100,
        arrival: "just got to the gym",
        days: [0],
      },
    ]);
    eq(activity?.pace, pace, `saving keeps the fine-tuned reply speed ${pace} exactly`);
  }
  check(
    tuned.every((pace) => !PACE_OPTIONS.some((option) => option.value === pace)),
    "…and those values really are outside the six options the editor offers",
  );
}

/* --------------------------------------------------------------------------
   Fixtúra: sedem dní, každý s vlastným tvarom — to, čo by mal model vrátiť
-------------------------------------------------------------------------- */

type RawActivity = Record<string, unknown>;

const DAY_SHAPES: Array<[string, string[]]> = [
  ["mon", ["kitchen", "gym", "home"]],
  ["tue", ["kitchen", "cafe", "car"]],
  ["wed", ["kitchen", "outside", "gym"]],
  ["thu", ["kitchen", "bathroom", "cafe"]],
  ["fri", ["kitchen", "gym", "outside"]],
  ["sat", ["cafe", "outside", "bathroom"]],
  ["sun", ["home", "kitchen", "bedroom"]],
];

function goodActivities(): RawActivity[] {
  const out: RawActivity[] = [];
  DAY_SHAPES.forEach(([day, rooms]) => {
    rooms.forEach((room, index) => {
      out.push({
        room,
        doing: `she is in the ${room} on ${day}, taking it easy`,
        reply_speed: PACE_OPTIONS[index % PACE_OPTIONS.length].value,
        minutes_min: 40 + index * 10,
        minutes_max: 40 + index * 10 + 35,
        on_arrival: index === 0 ? "" : `just got to the ${room}`,
        days: [day],
      });
    });
  });
  return out;
}

function good(): Record<string, unknown> {
  return {
    wake_weekday: { from: "08:20", to: "09:35" },
    wake_weekend: { from: "10:10", to: "11:50" },
    activities: goodActivities(),
    night: {
      room: "bedroom",
      doing: "she is in bed, not sleepy yet",
      reply_speed: 0.5,
      on_arrival: "just got into bed",
    },
  };
}

/* ------------------------------------------------------------- happy path */
{
  const result = mapScheduleDraft(good());
  check(Boolean(result.draft), "a valid answer produces a draft");
  eq(result.errors.length, 0, "a valid answer has no errors");
  eq(result.warnings.length, 0, "a valid answer has no warnings either");

  const draft = result.draft!;
  eq(draft.wake_weekday_start_min, 8 * 60 + 20, "weekday wake start is parsed from HH:MM");
  eq(draft.wake_weekday_end_min, 9 * 60 + 35, "weekday wake end is parsed from HH:MM");
  eq(draft.wake_weekend_start_min, 10 * 60 + 10, "weekend wake start is parsed");
  eq(draft.wake_weekend_end_min, 11 * 60 + 50, "weekend wake end is parsed");
  eq(draft.night_place, "bedroom", "the night room comes through");
  eq(draft.night_pace, 0.5, "the night reply speed comes through");
  eq(draft.activities.length, 21, "every activity survives");

  // Model nikdy nevidel naše mená stĺpcov — preklad robí výhradne mapper.
  const keys = Object.keys(draft.activities[0]).sort().join(",");
  eq(
    keys,
    "arrival,days,max_minutes,min_minutes,pace,place,what",
    "the mapper emits our column names, not the model's",
  );
  check(
    !JSON.stringify(SCHEDULE_SYSTEM_PROMPT).includes("min_minutes"),
    "the prompt never names one of our columns",
  );
  check(
    draft.activities.every((a) => (PLACES as readonly string[]).includes(a.place)),
    "every place is a real ambience key",
  );
  check(
    draft.activities.every((a) => PACE_OPTIONS.some((o) => o.value === a.pace)),
    "every reply speed is one we offer",
  );
  check(
    draft.activities.every((a) => a.max_minutes - a.min_minutes >= 10),
    "every duration is a real range, not a fixed length",
  );
  eq(draft.activities[0].days.join(","), "0", `"mon" maps to weekday 0`);
  eq(draft.activities[20].days.join(","), "6", `"sun" maps to weekday 6`);

  // Ten istý whitelist, aký použije ručný editor pri ukladaní: čo vyjde
  // z modelu, musí prejsť ním bez zmeny, inak by AI cesta ukladala niečo iné.
  const renormalised = normaliseActivities(draft.activities);
  eq(
    JSON.stringify(renormalised),
    JSON.stringify(draft.activities),
    "the mapped draft survives the manual form's whitelist untouched",
  );

  // A naozaj z toho vyjde deň — sedem rôznych, každý s nocou na konci.
  const shapes = new Set<string>();
  for (let day = 0; day <= 6; day++) {
    const blocks = previewDay(
      { ...draft, night_pace: draft.night_pace },
      day,
      "test",
    );
    check(blocks.length >= 3, `day ${day} generates a day with something in it`);
    eq(blocks[blocks.length - 1].to, 26 * 60 + 30, `day ${day} runs to 02:30`);
    shapes.add(blocks.map((b) => b.place).join(">"));
  }
  eq(shapes.size, 7, "all seven generated days have a different shape");
}

/* ------------------------------------------------------- nie je to ani objekt */
{
  for (const junk of [null, undefined, "a schedule", 42, [1, 2, 3]]) {
    const result = mapScheduleDraft(junk);
    check(!result.draft, `${JSON.stringify(junk)} is refused`);
    check(result.errors.length > 0, `${JSON.stringify(junk)} says why`);
  }
}

/* ------------------------------------------------------------ zlá miestnosť */
{
  const raw = good();
  (raw.activities as RawActivity[])[3].room = "nightclub";
  const result = mapScheduleDraft(raw);
  check(!result.draft, "an invented room is refused");
  check(mentions(result.errors, "nightclub"), "the error names the invented room");

  // Miestnosť sa nesmie „opraviť" na `home` potichu: model by sa to nedozvedel
  // a klientka by mala hlasovku z obývačky uprostred fitka.
  const nightRoom = good();
  (nightRoom.night as RawActivity).room = "spaceship";
  check(!mapScheduleDraft(nightRoom).draft, "an invented night room is refused too");

  // Veľké písmená a medzery okolo sú preklep, nie výmysel.
  const sloppy = good();
  (sloppy.activities as RawActivity[])[0].room = "  KITCHEN ";
  const ok = mapScheduleDraft(sloppy);
  check(Boolean(ok.draft), "a room with stray case/spacing still maps");
  eq(ok.draft?.activities[0].place, "kitchen", "it maps to the canonical key");
}

/* ------------------------------------------- pevné časy namiesto rozsahov */
{
  // Jedno pevné trvanie je preklep — rozšíri sa a povie sa to.
  const one = good();
  const acts = one.activities as RawActivity[];
  acts[0].minutes_min = 90;
  acts[0].minutes_max = 90;
  const patched = mapScheduleDraft(one);
  check(Boolean(patched.draft), "one fixed duration is repaired, not refused");
  check(mentions(patched.warnings, "fixed length"), "and the repair is reported");
  check(
    (patched.draft?.activities[0].max_minutes ?? 0) -
      (patched.draft?.activities[0].min_minutes ?? 0) >=
      10,
    "the repaired duration is a real range",
  );

  // Celý deň na pevné časy je rozvrh z papiera — to ide modelu späť.
  const all = good();
  for (const activity of all.activities as RawActivity[]) {
    activity.minutes_min = 60;
    activity.minutes_max = 60;
  }
  const rejected = mapScheduleDraft(all);
  check(!rejected.draft, "a schedule of fixed lengths is refused");
  check(
    mentions(rejected.errors, "no real duration range"),
    "the error tells the model what a range means",
  );
}

/* ---------------------------------------------------- nezmyselné trvania */
{
  const zero = good();
  (zero.activities as RawActivity[])[2].minutes_min = 0;
  check(!mapScheduleDraft(zero).draft, "a zero-minute activity is refused");

  const huge = good();
  (huge.activities as RawActivity[])[2].minutes_max = 99999;
  const hugeResult = mapScheduleDraft(huge);
  check(!hugeResult.draft, "a 99999-minute activity is refused");
  check(
    mentions(hugeResult.errors, `${MIN_DURATION} and ${MAX_DURATION}`),
    "the error states the range we accept",
  );

  const words = good();
  (words.activities as RawActivity[])[2].minutes_min = "about an hour";
  check(!mapScheduleDraft(words).draft, "a duration written in words is refused");

  // Prehodené hranice sú preklep, nie výmysel — narovnajú sa.
  const flipped = good();
  (flipped.activities as RawActivity[])[1].minutes_min = 120;
  (flipped.activities as RawActivity[])[1].minutes_max = 45;
  const straight = mapScheduleDraft(flipped);
  check(Boolean(straight.draft), "back-to-front minutes are straightened out");
  eq(straight.draft?.activities[1].min_minutes, 45, "the smaller one becomes the minimum");
  eq(straight.draft?.activities[1].max_minutes, 120, "the bigger one becomes the maximum");
  check(mentions(straight.warnings, "back-to-front"), "and it is reported");
}

/* ------------------------------------------------------------ chýbajúce dni */
{
  // Streda vypadla úplne.
  const gap = good();
  gap.activities = (gap.activities as RawActivity[]).filter(
    (a) => !(a.days as string[]).includes("wed"),
  );
  const gapResult = mapScheduleDraft(gap);
  check(!gapResult.draft, "a week with an empty day is refused");
  check(mentions(gapResult.errors, "Wednesday"), "the error names the empty day");

  // Deň s jedinou činnosťou je tiež diera — od rána do noci jedna vec.
  const thin = good();
  const kept = (thin.activities as RawActivity[]).filter(
    (a) => !(a.days as string[]).includes("sun"),
  );
  kept.push({
    room: "home",
    doing: "she is at home doing nothing much",
    reply_speed: 1,
    minutes_min: 60,
    minutes_max: 120,
    on_arrival: "",
    days: ["sun"],
  });
  thin.activities = kept;
  const thinResult = mapScheduleDraft(thin);
  check(!thinResult.draft, "a day with a single activity is refused");
  check(mentions(thinResult.errors, "Sunday"), "the error names the thin day");

  // Činnosť bez jediného dňa.
  const nowhere = good();
  (nowhere.activities as RawActivity[])[0].days = [];
  check(!mapScheduleDraft(nowhere).draft, "an activity on no day at all is refused");

  // Vymyslené mená dní sa zahodia — a keď z toho neostane nič, je to chyba.
  const invented = good();
  (invented.activities as RawActivity[])[0].days = ["someday", "caturday"];
  check(!mapScheduleDraft(invented).draft, "invented day names are refused");

  // Celé mená aj čísla sú v poriadku: model si vyberie, my rozumieme obom.
  const spelled = good();
  (spelled.activities as RawActivity[])[0].days = ["Monday"];
  (spelled.activities as RawActivity[])[1].days = [0];
  const spelledResult = mapScheduleDraft(spelled);
  check(Boolean(spelledResult.draft), `"Monday" and 0 both mean weekday 0`);
}

/* -------------------------------------------- sedem rovnakých dní = vzor */
{
  // Presne to, čo model spraví, keď sa naň netlačí: jeden deň sedemkrát.
  const same = good();
  same.activities = [
    {
      room: "kitchen",
      doing: "she is having coffee",
      reply_speed: 0.8,
      minutes_min: 40,
      minutes_max: 75,
      on_arrival: "just got up",
      days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    },
    {
      room: "gym",
      doing: "she is at the gym",
      reply_speed: 2.4,
      minutes_min: 60,
      minutes_max: 100,
      on_arrival: "just got to the gym",
      days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    },
  ];
  const result = mapScheduleDraft(same);
  check(!result.draft, "the same day seven times over is refused");
  check(
    mentions(result.errors, "same places in the same order"),
    "the error explains that each weekday needs its own shape",
  );

  // Aj len dva rovnaké dni z siedmich sú vzor, ktorý je po týždni vidieť.
  const twins = good();
  twins.activities = (twins.activities as RawActivity[]).map((a) =>
    (a.days as string[])[0] === "wed"
      ? { ...a, room: ["kitchen", "gym", "home"][DAY_SHAPES[2][1].indexOf(a.room as string)] }
      : a,
  );
  const twinsResult = mapScheduleDraft(twins);
  check(!twinsResult.draft, "two identical days out of seven are refused");
  check(
    mentions(twinsResult.errors, "Monday") && mentions(twinsResult.errors, "Wednesday"),
    "the error names both days that collide",
  );
}

/* ----------------------------------------------------------- zlá rýchlosť */
{
  // Mimo rozsahu = model si vymyslel škálu.
  const wild = good();
  (wild.activities as RawActivity[])[0].reply_speed = 99;
  const wildResult = mapScheduleDraft(wild);
  check(!wildResult.draft, "a reply speed off our scale is refused");
  check(mentions(wildResult.errors, "reply_speed"), "the error names the field");

  const negative = good();
  (negative.activities as RawActivity[])[0].reply_speed = -1;
  check(!mapScheduleDraft(negative).draft, "a negative reply speed is refused");

  const wordy = good();
  (wordy.activities as RawActivity[])[0].reply_speed = "fast";
  check(!mapScheduleDraft(wordy).draft, `a reply speed written as "fast" is refused`);

  // V rozsahu, ale mimo ponuky: prilepí sa na najbližšiu, nech klient nedostane
  // násobič, ktorý mu editor ani nevie zobraziť.
  const between = good();
  (between.activities as RawActivity[])[0].reply_speed = 1.2;
  const snapped = mapScheduleDraft(between);
  check(Boolean(snapped.draft), "a speed between two options still maps");
  eq(snapped.draft?.activities[0].pace, 1, "it snaps to the nearest option we offer");
  check(mentions(snapped.warnings, "nearest"), "and the snap is reported");
}

/* ------------------------------------------------------- okná vstávania */
{
  const missing = good();
  delete (missing as Record<string, unknown>).wake_weekday;
  check(!mapScheduleDraft(missing).draft, "a missing wake window is refused");

  const junk = good();
  missingClock(junk, "half past eight");
  check(!mapScheduleDraft(junk).draft, "a wake time in words is refused");

  const impossible = good();
  missingClock(impossible, "26:70");
  check(!mapScheduleDraft(impossible).draft, "an impossible clock time is refused");

  // Presný čas namiesto okna je budík, nie človek — rozšíri sa.
  const alarm = good();
  alarm.wake_weekday = { from: "08:00", to: "08:00" };
  const widened = mapScheduleDraft(alarm);
  check(Boolean(widened.draft), "a single wake moment is widened, not refused");
  check(
    (widened.draft?.wake_weekday_end_min ?? 0) - (widened.draft?.wake_weekday_start_min ?? 0) >=
      10,
    "the widened wake window is a real window",
  );
  check(mentions(widened.warnings, "single moment"), "and the widening is reported");

  // Prehodené hranice sa narovnajú.
  const flipped = good();
  flipped.wake_weekend = { from: "12:00", to: "10:30" };
  const straight = mapScheduleDraft(flipped);
  eq(straight.draft?.wake_weekend_start_min, 10 * 60 + 30, "the earlier time becomes the start");
  eq(straight.draft?.wake_weekend_end_min, 12 * 60, "the later one becomes the end");
}

function missingClock(raw: Record<string, unknown>, value: string): void {
  raw.wake_weekday = { from: value, to: "09:00" };
}

/* --------------------------------------------------------------- noc */
{
  const missing = good();
  delete (missing as Record<string, unknown>).night;
  check(!mapScheduleDraft(missing).draft, "a missing night block is refused");

  const empty = good();
  (empty.night as RawActivity).doing = "   ";
  const emptyResult = mapScheduleDraft(empty);
  check(!emptyResult.draft, "an empty night line is refused");
  check(mentions(emptyResult.errors, "night"), "the error says it is the night");
}

/* ------------------------------------------------------------- text a kľúče */
{
  // Kľúč navyše sa zahodí a povie sa to — nesmie sa dostať do updatu.
  const extra = good();
  extra.notes = "I also added a mood tracker";
  extra.model_id = "00000000-0000-0000-0000-000000000000";
  (extra.activities as RawActivity[])[0].intensity = "high";
  const result = mapScheduleDraft(extra);
  check(Boolean(result.draft), "extra top-level keys do not sink the answer");
  check(mentions(result.warnings, "unexpected key"), "but they are reported");
  check(
    !Object.keys(result.draft ?? {}).includes("notes") &&
      !Object.keys(result.draft ?? {}).includes("model_id"),
    "and they never reach the draft",
  );
  check(
    !Object.keys(result.draft?.activities[0] ?? {}).includes("intensity"),
    "an extra key inside an activity is dropped too",
  );

  // Dlhý text sa oreže, markdown a nové riadky sa zrovnajú — ide to do promptu.
  const long = good();
  (long.activities as RawActivity[])[0].doing = `**she is** cooking\n\n  something   slow ${"x".repeat(400)}`;
  const longResult = mapScheduleDraft(long);
  const what = longResult.draft?.activities[0].what ?? "";
  check(what.length <= MAX_TEXT, `an over-long line is cut to ${MAX_TEXT} characters`);
  check(!what.includes("\n"), "newlines are flattened out of the line");
  check(!what.includes("  "), "runs of spaces are collapsed");

  // Prázdny „doing" je činnosť, o ktorej nemá čo povedať.
  const blank = good();
  (blank.activities as RawActivity[])[0].doing = "";
  check(!mapScheduleDraft(blank).draft, "an activity with no description is refused");

  // Prázdne „activities".
  const none = good();
  none.activities = [];
  check(!mapScheduleDraft(none).draft, "an empty day is refused");
  none.activities = "a busy week";
  check(!mapScheduleDraft(none).draft, "activities that are not an array are refused");

  // Stovky činností: strop je v migrácii 022, tak ho drž aj tu.
  const flood = good();
  flood.activities = [
    ...(good().activities as RawActivity[]),
    ...Array.from({ length: 200 }, () => ({
      room: "home",
      doing: "she is at home",
      reply_speed: 1,
      minutes_min: 30,
      minutes_max: 60,
      on_arrival: "",
      days: ["mon"],
    })),
  ];
  const flooded = mapScheduleDraft(flood);
  check(
    (flooded.draft?.activities.length ?? 999) <= MAX_ACTIVITIES,
    `no more than ${MAX_ACTIVITIES} activities survive`,
  );
  check(mentions(flooded.warnings, "first"), "the truncation is reported");
}

/* --------------------------------------------------------------- prompt */
{
  for (const place of PLACES) {
    check(
      SCHEDULE_SYSTEM_PROMPT.includes(`"${place}"`),
      `the schema lists the room "${place}"`,
    );
  }
  for (const option of PACE_OPTIONS) {
    check(
      SCHEDULE_SYSTEM_PROMPT.includes(`  ${option.value} —`),
      `the schema lists the reply speed ${option.value}`,
    );
  }
  check(
    SCHEDULE_SYSTEM_PROMPT.includes("ANY LANGUAGE") &&
      SCHEDULE_SYSTEM_PROMPT.includes("English"),
    "the schema demands English output whatever language the description arrives in",
  );
  check(
    SCHEDULE_SYSTEM_PROMPT.includes("RANGES, never fixed"),
    "the schema states the range rule the mapper enforces",
  );
  check(
    SCHEDULE_SYSTEM_PROMPT.includes("DIFFERENT shape"),
    "the schema states the different-days rule the mapper enforces",
  );
  check(
    SCHEDULE_SYSTEM_PROMPT.includes("invent something ordinary"),
    "the schema tells the model to fill a thin description rather than leave a hole",
  );
  check(
    SCHEDULE_SYSTEM_PROMPT.includes("raw JSON") || SCHEDULE_SYSTEM_PROMPT.includes("ONE JSON"),
    "the schema demands strict JSON",
  );

  const message = buildScheduleUserMessage("vstáva o jedenástej a chodí do fitka", "Košice");
  check(message.includes("Košice"), "the user message carries the city");
  check(message.includes("fitka"), "the user message carries the operator's own words");
  check(
    !buildScheduleUserMessage("something", "").includes("She lives in"),
    "no city means the prompt does not invent one",
  );
}

console.log(`${passed} passed, ${failed} failed`);
if (failed > 0) process.exitCode = 1;

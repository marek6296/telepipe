/**
 * Porovnávacie stránky — kontrola toho, čo sa na nich nesmie objaviť.
 *
 * Toto nie je test kódu, je to test OBSAHU. Stránka o konkurencii je jediné
 * miesto na webe, kde sa dá jednou vetou vyrobiť právny problém alebo tenká
 * doorway stránka, ktorú Google zahodí aj s doménou. Preto sa kontroluje:
 *
 *  - že je pri každom mene priznané vlastníctvo značky,
 *  - že sa nikde netvrdí cena konkurencie (mení sa, zajtra by sme klamali),
 *  - že sa o nich nepíše hanlivo,
 *  - že každá stránka má vlastný text, nie vymenené kľúčové slovo.
 *
 * Spustenie:  npm run test:alternatives
 */
import {
  ALTERNATIVES,
  ALTERNATIVE_SLUGS,
  findAlternative,
  trademarkNote,
} from "../lib/alternatives.ts";

let failed = 0;
let passed = 0;

function check(condition: boolean, message: string): void {
  if (condition) {
    passed++;
    return;
  }
  failed++;
  console.error(`  ✗ ${message}`);
}

/** Celý text stránky ako jeden reťazec — na hľadanie zakázaných vecí. */
function textOf(item: (typeof ALTERNATIVES)[number]): string {
  return [
    item.title,
    item.description,
    item.eyebrow,
    item.lead,
    ...item.highlights.flatMap((h) => [h.title, h.body]),
    ...item.sections.flatMap((s) => [s.title, ...s.paragraphs, ...(s.points ?? [])]),
    ...item.faq.flatMap((f) => [f.q, f.a]),
  ].join("\n");
}

/* --- tvar a jedinečnosť --------------------------------------------------- */

check(ALTERNATIVES.length >= 4, "aspoň štyri porovnania, inak rozcestník nemá zmysel");
check(
  new Set(ALTERNATIVE_SLUGS).size === ALTERNATIVE_SLUGS.length,
  "slugy sa nesmú opakovať — dve stránky na jednej adrese",
);

for (const item of ALTERNATIVES) {
  const kde = `[${item.slug}]`;

  check(/^[a-z0-9-]+$/.test(item.slug), `${kde} slug je len malé písmená a pomlčky`);
  check(findAlternative(item.slug) === item, `${kde} sa dá nájsť podľa slugu`);

  // Google reže titulok okolo 60 znakov a popis okolo 160. Dlhší nie je chyba,
  // ale je to text, ktorý nikto neuvidí.
  check(item.title.length <= 60, `${kde} titulok ${item.title.length} znakov (max 60)`);
  check(
    item.description.length >= 110 && item.description.length <= 165,
    `${kde} popis ${item.description.length} znakov (110–165)`,
  );

  check(item.highlights.length >= 3, `${kde} aspoň tri hlavné body`);
  check(item.sections.length >= 2, `${kde} aspoň dve sekcie`);
  check(item.faq.length >= 3, `${kde} aspoň tri otázky do FAQ`);

  const text = textOf(item);
  check(text.length >= 1800, `${kde} má len ${text.length} znakov — na tenkú stránku stačí, na dobrú nie`);
  check(text.includes(item.name), `${kde} musí menovať ${item.name}`);
}

/* --- čo sa na nich NESMIE objaviť ---------------------------------------- */

for (const item of ALTERNATIVES) {
  const kde = `[${item.slug}]`;
  const text = textOf(item);

  // Ceny konkurencie. Naša vlastná cena je v poriadku (vieme ju), ale suma
  // vedľa cudzieho mena je tvrdenie, ktoré o mesiac nemusí platiť.
  const ceny = text.match(/\$\s?\d/g) ?? [];
  check(ceny.length === 0, `${kde} nesmie tvrdiť sumy — nájdené: ${ceny.join(", ")}`);

  // Hanlivé tvrdenia. Porovnanie konvertuje, útok nie — a útok je aj to, čo
  // z porovnávacej stránky robí právny problém.
  const hanlive = [
    "scam", "useless", "garbage", "terrible", "rip-off", "ripoff",
    "worst", "broken", "doesn't work", "does not work", "fake",
  ];
  for (const slovo of hanlive) {
    check(
      !text.toLowerCase().includes(slovo),
      `${kde} obsahuje hanlivé „${slovo}"`,
    );
  }

  // Superlatívy o nás. „Najlepší" sa nedá doložiť a čitateľ mu neverí.
  for (const slovo of ["the best ", "#1 ", "number one"]) {
    check(!text.toLowerCase().includes(slovo), `${kde} obsahuje nedoložiteľné „${slovo.trim()}"`);
  }
}

/* --- vlastníctvo značky --------------------------------------------------- */

for (const item of ALTERNATIVES) {
  const note = trademarkNote(item.name);
  check(note.includes(item.name), `[${item.slug}] veta o značke menuje ${item.name}`);
  check(note.includes("not affiliated"), `[${item.slug}] veta o značke priznáva nezávislosť`);
  check(note.includes("trademark"), `[${item.slug}] veta o značke spomína ochrannú známku`);
}

/* --- žiadne dve stránky nie sú tá istá stránka ---------------------------- */

for (let i = 0; i < ALTERNATIVES.length; i++) {
  for (let j = i + 1; j < ALTERNATIVES.length; j++) {
    const a = ALTERNATIVES[i];
    const b = ALTERNATIVES[j];
    check(a.lead !== b.lead, `[${a.slug}] a [${b.slug}] majú rovnaký úvod`);
    const otazkyA = new Set(a.faq.map((f) => f.q));
    const spolocne = b.faq.filter((f) => otazkyA.has(f.q));
    check(
      spolocne.length === 0,
      `[${a.slug}] a [${b.slug}] zdieľajú otázku: ${spolocne[0]?.q ?? ""}`,
    );
  }
}

/* --- CupidBot: stránka musí povedať pravdu -------------------------------- */

{
  // Je to iný trh (randenie, nie tvorkyne). Keby stránka predstierala, že to
  // je náhrada, priviedla by ľudí, ktorí odídu za tri sekundy — a to Google
  // vidí. Musí tam byť jasné „toto nie je to isté".
  const cupid = findAlternative("cupidbot-alternative");
  check(cupid !== undefined, "stránka o CupidBote existuje");
  if (cupid) {
    const text = textOf(cupid).toLowerCase();
    check(text.includes("dating"), "CupidBot: pomenuje, že ide o randenie");
    check(
      text.includes("this is not it") || text.includes("no dating-app integration"),
      "CupidBot: musí priznať, že to nie je náhrada",
    );
  }
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

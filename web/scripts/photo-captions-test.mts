/**
 * Popisky fotiek: JSON od modelu → naše stĺpce.
 *
 * Testuje sa nepriateľský výstup, nie ten pekný. Popis, ktorý sadne na CUDZIU
 * fotku, je horší než žiadny: modelka pošle fotku z postele a napíše k nej
 * vetu o posilňovni. Preto sa fotky párujú cez index, ktorý sme si očíslovali
 * sami, a všetko mimo rozsahu sa zahadzuje.
 *
 * Spustenie:  npm run test:captions
 */
import {
  MAX_CAPTION,
  MAX_SITUATION,
  MAX_PHOTOS,
  folderMeaning,
  isKnownFolder,
  mapCaptions,
  systemPrompt,
  type PhotoForCaption,
} from "../lib/photo-captions.ts";

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

const FOTKY: PhotoForCaption[] = [
  { id: 101, url: "https://example.test/a.jpg" },
  { id: 102, url: "https://example.test/b.jpg" },
  { id: 103, url: "https://example.test/c.jpg" },
];

function odpoved(rows: unknown, shared = "black silk slip, one evening") {
  return { shared, photos: rows };
}

/* --- párovanie ------------------------------------------------------------ */

{
  const { drafts, shared, errors } = mapCaptions(
    odpoved([
      { index: 1, caption: "black silk slip, sitting on the bed", situation: "late evening" },
      { index: 2, caption: "same slip, lying down, lamp behind her", situation: "late evening" },
      { index: 3, caption: "close up, same slip, phone in hand", situation: "in bed, winding down" },
    ]),
    FOTKY,
  );
  check(drafts.length === 3, "všetky tri fotky dostanú popis");
  check(drafts[0].id === 101 && drafts[2].id === 103, "index sa páruje na správne id");
  check(shared.includes("silk"), "spoločný menovateľ albumu sa vracia");
  check(errors.length === 0, "čistá odpoveď nemá výhrady");
}

{
  // Model si vymyslel štvrtú fotku — nesmie sadnúť na nič.
  const { drafts, errors } = mapCaptions(
    odpoved([
      { index: 1, caption: "ok", situation: "" },
      { index: 9, caption: "vymyslená", situation: "" },
    ]),
    FOTKY,
  );
  check(drafts.length === 1, "index mimo rozsahu sa zahodí");
  check(drafts[0].id === 101, "zvyšok sa nepomiešal");
  check(errors.some((e) => e.includes("9")), "o vymyslenej fotke sa povie");
}

{
  const { drafts } = mapCaptions(
    odpoved([
      { index: 2, caption: "prvá", situation: "" },
      { index: 2, caption: "druhá na tú istú", situation: "" },
    ]),
    FOTKY,
  );
  check(drafts.length === 1 && drafts[0].caption === "prvá", "duplicitný index sa neprepíše");
}

{
  const { drafts, errors } = mapCaptions(
    odpoved([{ index: 1, caption: "   ", situation: "večer" }]),
    FOTKY,
  );
  check(drafts.length === 0, "prázdny popis sa nezapíše");
  check(errors.length > 0, "prázdny popis sa ohlási");
}

{
  // Neúplná odpoveď sa NEZAHADZUJE celá — klient zaplatil za volanie.
  const { drafts, errors } = mapCaptions(odpoved([{ index: 1, caption: "ok" }]), FOTKY);
  check(drafts.length === 1, "čiastočná odpoveď sa použije");
  check(errors.some((e) => e.includes("2")), "chýbajúce fotky sa spočítajú");
  check(drafts[0].situation === "", "chýbajúca situácia je prázdna, nie 'undefined'");
}

/* --- odolnosť voči nezmyslom --------------------------------------------- */

for (const [popis, vstup] of [
  ["null", null],
  ["reťazec", "hotovo"],
  ["pole", []],
  ["objekt bez photos", { shared: "x" }],
  ["photos nie je pole", { photos: "x" }],
] as [string, unknown][]) {
  const { drafts, errors } = mapCaptions(vstup, FOTKY);
  check(drafts.length === 0 && errors.length > 0, `${popis} neprejde a povie prečo`);
}

{
  const { drafts } = mapCaptions(
    odpoved([{ index: 1, caption: "x".repeat(500), situation: "y".repeat(500) }]),
    FOTKY,
  );
  check(drafts[0].caption.length === MAX_CAPTION, "popis sa oreže na strop");
  check(drafts[0].situation.length === MAX_SITUATION, "situácia sa oreže na strop");
}

{
  const { drafts } = mapCaptions(
    odpoved([{ index: 1, caption: "prvý\n\n  riadok   a druhý", situation: "" }]),
    FOTKY,
  );
  check(
    drafts[0].caption === "prvý riadok a druhý",
    "viacriadkový popis sa zloží do jedného riadku",
  );
}

/* --- zadanie pre model ---------------------------------------------------- */

{
  const prompt = systemPrompt("Simona", "bed_night");
  check(prompt.includes("Simona"), "prompt pozná meno modelky");
  check(prompt.includes("in bed late at night"), "prompt povie, čo album znamená");
  check(
    prompt.includes("never sent as a message"),
    "prompt hovorí, že popis NIE JE text do chatu — inak píše zvodné vety",
  );
  check(prompt.includes("SAME WAY"), "prompt žiada konzistenciu naprieč albumom");
  check(prompt.includes("English"), "výstup musí byť anglicky");
  check(prompt.includes('"situation"'), "prompt pýta aj kedy sa fotka hodí");
}

{
  check(folderMeaning("gym").includes("gym"), "album gym má svoj význam");
  check(folderMeaning("neznámy") === folderMeaning("universal"), "neznámy album spadne na univerzál");
  check(isKnownFolder("home") && !isKnownFolder("kuchyna"), "pozná len naše albumy");
  check(MAX_PHOTOS <= 12, "dávka je dosť malá, aby model udržal konzistenciu");
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

/**
 * Katalóg jazykov — stráži, že sa web a worker nerozišli.
 *
 * Zoznam žije na dvoch miestach (`lib/languages.ts` a `worker/src/jazyky.py`),
 * lebo web ho vykresľuje a worker prekladá do promptu. Keď v jednom pribudne
 * jazyk a v druhom nie, klient si ho navolí a modelka oň nikdy nezavadí — bez
 * jedinej chybovej hlášky.
 *
 * Spustenie: npm run test:languages
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  LANGUAGES,
  LEVELS,
  MAX_EXTRA,
  normalizeExtra,
  normalizePrimary,
} from "../lib/languages.ts";

const python = readFileSync(new URL("../../worker/src/jazyky.py", import.meta.url), "utf8");

// Kódy musia sedieť na kus. Nie „približne" — worker vie preložiť len to, čo má.
const workerCodes = [...python.matchAll(/^\s{4}"([a-z]{2})": "([^"]+)",$/gm)].map((m) => ({
  code: m[1],
  name: m[2],
}));
assert.ok(workerCodes.length > 5, "katalóg workera sa nepodarilo prečítať");

assert.deepEqual(
  LANGUAGES.map((l) => l.code).sort(),
  workerCodes.map((l) => l.code).sort(),
  "kódy jazykov sa medzi webom a workerom rozišli",
);
for (const { code, name } of workerCodes) {
  assert.equal(
    LANGUAGES.find((l) => l.code === code)?.name,
    name,
    `jazyk ${code} sa volá inak vo webe než vo workerovi`,
  );
}
console.log(`  ok — ${LANGUAGES.length} jazykov sedí s workerom`);

// Úrovne tiež — worker podľa nich vyberá vetu o štýle písania.
const workerLevels = [...python.matchAll(/^\s{4}"([A-C][12])": \($/gm)].map((m) => m[1]);
assert.deepEqual(
  LEVELS.map((l) => l.value).sort(),
  [...new Set(workerLevels)].sort(),
  "úrovne sa medzi webom a workerom rozišli",
);
console.log("  ok — úrovne sedia s workerom");

// Očista: čokoľvek pokazené musí ticho vypadnúť, nie zhodiť formulár.
assert.deepEqual(normalizeExtra(null, "en"), []);
assert.deepEqual(normalizeExtra("nie je pole", "en"), []);
assert.deepEqual(normalizeExtra([{ code: "xx", level: "B1" }], "en"), []);
assert.deepEqual(normalizeExtra([{ code: "de", level: "Z9" }], "en"), []);
assert.deepEqual(normalizeExtra([{ code: "de" }], "en"), []);
console.log("  ok — pokazené položky ticho vypadnú");

// Hlavný jazyk sa nesmie zopakovať medzi vedľajšími — DB by patch odmietla.
assert.deepEqual(normalizeExtra([{ code: "en", level: "B1" }], "en"), []);
assert.deepEqual(
  normalizeExtra([{ code: "de", level: "B1" }, { code: "de", level: "C1" }], "en"),
  [{ code: "de", level: "B1" }],
  "duplicita musí padnúť na prvý výskyt",
);
console.log("  ok — duplicity a hlavný jazyk sa odfiltrujú");

// Strop musí sedieť s CHECK constraintom, inak databáza odmietne uložiť to,
// čo formulár dovolil navoliť.
const priveľa = LANGUAGES.filter((l) => l.code !== "en")
  .slice(0, MAX_EXTRA + 2)
  .map((l) => ({ code: l.code, level: "B1" }));
assert.equal(normalizeExtra(priveľa, "en").length, MAX_EXTRA);
console.log(`  ok — najviac ${MAX_EXTRA} vedľajšie jazyky`);

// Veľké písmená a medzery z formulára nesmú položku zahodiť.
assert.deepEqual(normalizeExtra([{ code: " DE ", level: "b1" }], "en"), [
  { code: "de", level: "B1" },
]);
assert.equal(normalizePrimary(" EN "), "en");
assert.equal(normalizePrimary("xx"), "en", "neznámy hlavný jazyk padá na angličtinu");
console.log("  ok — tvar sa očistí, nie zahodí");

console.log("\nlanguages-test: OK");

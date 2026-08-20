/**
 * Zhoda dvoch kópií: `worker/src/checkout.py` a `web/lib/checkout.ts`.
 *
 * Odkaz sa skladá na dvoch miestach — pri odpisovaní (worker, Python) a pri
 * kliknutí na krátky odkaz (web, TypeScript). Keby sa rozišli, atribúcia by
 * fungovala len z jednej strany a platby by sa prestali dať spojiť s chatom.
 * Preto sa tu púšťajú OBE implementácie na tých istých vstupoch a porovnáva sa
 * výstup — nie „mala by robiť to isté", ale „robí to isté".
 *
 * Spustenie:  npm run test:checkout   (potrebuje python3 v PATH)
 */
import { execFileSync } from "node:child_process";

import { attributedLink, reference } from "../lib/checkout.ts";

let failed = 0;
let passed = 0;

function check(condition: boolean, message: string): void {
  if (condition) passed++;
  else {
    failed++;
    console.error(`✗ ${message}`);
  }
}

const PRIPADY: Array<[string, number]> = [
  ["https://fanvue.com/simona", 424242],
  ["https://fanvue.com/simona?utm=x", 424242],
  ["https://fanvue.com/simona#about", 424242],
  ["https://fanvue.com/simona?a=1#about", 7],
  ["https://fanvue.com/simona?client_reference_id=tg-1", 424242],
  ["https://www.fanvue.com/simona/", -55],
  ["https://onlyfans.com/simona", 424242],
  ["", 424242],
  ["   https://fanvue.com/simona   ", 1],
];

// Python vráti svoje výsledky ako JSON, aby sa porovnávali hodnoty, nie dojmy.
const script = `
import json, sys
sys.path.insert(0, "../worker/src")
import checkout
vstupy = json.loads(sys.argv[1])
print(json.dumps([checkout.attributed(l, t) for l, t in vstupy]))
`;
const zPythonu: string[] = JSON.parse(
  execFileSync("python3", ["-c", script, JSON.stringify(PRIPADY)], {
    encoding: "utf8",
  }).trim(),
);

PRIPADY.forEach(([link, tgId], i) => {
  const zTypescriptu = attributedLink(link, tgId);
  check(
    zTypescriptu === zPythonu[i],
    `nezhoda pre ${JSON.stringify(link)} / ${tgId}:\n    python: ${JSON.stringify(zPythonu[i])}\n    web:    ${JSON.stringify(zTypescriptu)}`,
  );
});

check(reference(42) === "tg-42", "referencia má našu predponu");
check(reference(NaN) === "", "nečíslo nemá referenciu");

console.log(`${passed} passed, ${failed} failed`);
if (failed > 0) process.exitCode = 1;

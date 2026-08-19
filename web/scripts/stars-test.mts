/**
 * Cenník Telegram Stars — stráži, že cez Stars nikdy nepredávame pod cenu.
 *
 * Bez tejto kontroly by stačilo raz zle zaokrúhliť a každý nákup by nás stál
 * peniaze — potichu a pri každom klientovi.
 *
 * Spustenie: npm run test:stars
 */
import assert from "node:assert/strict";

import {
  APPROX_USD_PER_STAR_FOR_USER,
  STARS_MAX_USD,
  STARS_MIN_USD,
  STAR_OPTIONS,
  USD_PER_STAR,
  approxUserCostUsd,
  assertStarsProfitable,
  buildPayload,
  parsePayload,
  starsForUsd,
} from "../lib/stars.ts";
import { COINS_PER_USD } from "../lib/coins.ts";

// Kotva: oficiálna tabuľka Telegramu. Keby sa USD_PER_STAR raz zmenil bez toho,
// aby sa prepočítal cenník, spadne to tu a nie až na výplate.
for (const [stars, netUsd] of [[50, 0.65], [500, 6.5], [750, 9.75], [2500, 32.5]] as const) {
  assert.equal(
    Number((stars * USD_PER_STAR).toFixed(2)),
    netUsd,
    `${stars} ⭐ má vyniesť $${netUsd} podľa tabuľky Telegramu`,
  );
}
console.log("  ok — kurz sedí s oficiálnou tabuľkou");

// Nikdy nepredávame pod cenu.
assertStarsProfitable();
console.log("  ok — žiadna ponuka nie je pod cenou");

// Zaokrúhľuje sa NAHOR, nikdy nadol.
for (const usd of [5, 7, 10, 13, 20, 50, 137]) {
  const stars = starsForUsd(usd);
  assert.ok(stars * USD_PER_STAR >= usd, `$${usd} → ${stars} ⭐ je pod cenou`);
  assert.equal(stars % 10, 0, "počet Stars má byť zaokrúhlený na desiatku");
}
console.log("  ok — zaokrúhľovanie vždy nahor");

// Bonusy za objem pri Stars NEPLATIA — inak by veľký nákup cez Telegram
// prerobil, lebo poplatok je 35 %, nie 1 %.
for (const option of STAR_OPTIONS) {
  assert.equal(option.coins, option.usd * COINS_PER_USD, "žiadny bonus pri Stars");
}
console.log("  ok — bez bonusov za objem");

// Ponuka začína na malej sume: cez Telegram ľudia kupujú $10-20, nie $250.
assert.equal(STAR_OPTIONS[0].usd, STARS_MIN_USD);
assert.ok(STAR_OPTIONS.some((o) => o.usd === 10), "musí byť možnosť za $10");
assert.ok(STAR_OPTIONS.some((o) => o.usd === 20), "musí byť možnosť za $20");
console.log("  ok — ťažisko na malých sumách");

// Odhad ceny pre používateľa je len orientačný, ale musí byť VYŠŠÍ než náš net —
// inak by sme klientovi ukazovali nezmysel.
for (const option of STAR_OPTIONS) {
  assert.ok(
    approxUserCostUsd(option.stars) > option.stars * USD_PER_STAR,
    "cena pre používateľa musí byť vyššia než náš výnos",
  );
}
assert.ok(APPROX_USD_PER_STAR_FOR_USER > USD_PER_STAR);
console.log("  ok — odhad ceny pre klienta dáva zmysel");

/* -------------------------------------------------------------------------- */
/*  Payload — na ňom stojí, na čí účet pôjdu peniaze                           */
/* -------------------------------------------------------------------------- */

const ACC = "1e23e8bb-1aa7-451d-b5cd-f8c526653939";

{
  const round = parsePayload(buildPayload(ACC, 10));
  assert.deepEqual(round, { accountId: ACC, usd: 10 }, "payload sa musí prečítať späť");
}

// Čokoľvek podvrhnuté musí skončiť ako `null` — vtedy platbu odmietneme ešte
// pred stiahnutím peňazí, namiesto toho aby sme ju pripísali cudziemu účtu.
for (const zly of [
  "",
  "podvrh",
  `v1:${ACC}`,
  `v1:${ACC}:`,
  `v1:${ACC}:0`,
  `v1:${ACC}:-5`,
  `v1:${ACC}:abc`,
  `v2:${ACC}:10`,
  `v1:nie-je-uuid:10`,
  `v1:${ACC}:10:extra`,
  // Nad horný limit — inak by stačilo podvrhnúť obrovskú sumu.
  `v1:${ACC}:999999`,
]) {
  assert.equal(parsePayload(zly), null, `payload ${JSON.stringify(zly)} mal byť odmietnutý`);
}
console.log("  ok — podvrhnutý payload sa odmietne");

// Payload sa musí zmestiť do limitu Telegramu (1–128 bajtov).
{
  const bytes = Buffer.byteLength(buildPayload(ACC, STARS_MAX_USD), "utf8");
  assert.ok(bytes >= 1 && bytes <= 128, `payload má ${bytes} B, limit je 128`);
  console.log(`  ok — payload má ${bytes} B (limit 128)`);
}

console.log("\nPrehľad ponuky:");
for (const o of STAR_OPTIONS) {
  console.log(
    `  $${String(o.usd).padStart(3)} → ${String(o.stars).padStart(5)} ⭐ ` +
      `(klient zaplatí ~$${approxUserCostUsd(o.stars).toFixed(2)}, ` +
      `nám ostane $${(o.stars * USD_PER_STAR).toFixed(2)}, ` +
      `dostane ${o.coins.toLocaleString("en-US")} coinov)`,
  );
}

console.log("\nstars-test: OK");

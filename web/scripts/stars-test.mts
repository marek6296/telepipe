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
  COINS_PER_STAR,
  PLATFORM_FEE_PCT,
  STARS_MAX_USD,
  STAR_PACKS,
  SAFETY_MARGIN,
  USD_PER_STAR,
  approxUserCostUsd,
  assertStarsProfitable,
  buildPayload,
  coinsForUsd,
  parsePayload,
  starPack,
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

// Každý balík musí ostať nad cenou aj s rezervou.
for (const pack of STAR_PACKS) {
  const net = pack.stars * USD_PER_STAR;
  assert.ok(net >= pack.usd, `${pack.stars} ⭐ → $${pack.usd} je pod cenou`);
  // A ešte s rezervou — samotné „aspoň na svoje" je pri 0,1 % rozdiele ilúzia.
  assert.ok(
    net >= pack.usd / (1 - SAFETY_MARGIN),
    `${pack.stars} ⭐ nemá ${SAFETY_MARGIN * 100} % rezervu (vynesie $${net.toFixed(2)}, ` +
      `pripíšeme $${pack.usd})`,
  );
  assert.equal(pack.coins, coinsForUsd(pack.usd), "coiny a suma si musia odpovedať");
  assert.equal(pack.coins, pack.stars * COINS_PER_STAR, "kurz musí sedieť na COINS_PER_STAR");
}
console.log(`  ok — každý balík má ${SAFETY_MARGIN * 100} % rezervu`);

// VEĽKOSTI BALÍKOV. Toto je celý dôvod prechodu z vlastnej sumy na balíky:
// hviezdy sa nedajú kúpiť po kuse, takže faktúra musí pýtať presne toľko,
// koľko Telegram v jednom balíku predáva — inak klientovi ostanú zvyšky.
for (const pack of STAR_PACKS) {
  assert.ok(
    [500, 1000, 2500, 5000, 10_000].includes(pack.stars),
    `${pack.stars} ⭐ nie je veľkosť balíka, ktorý Telegram predáva`,
  );
}
assert.equal(STAR_PACKS[0].stars, 500, "najmenší balík je 500 ⭐");
console.log("  ok — veľkosti sedia na balíky Telegramu");

// Bonusy za objem pri Stars NEPLATIA — inak by veľký nákup cez Telegram
// prerobil, lebo poplatok je 35 %, nie 1 %. Kurz teda musí byť lineárny.
const kurzy = new Set(STAR_PACKS.map((p) => p.coins / p.stars));
assert.equal(kurzy.size, 1, `balíky majú rôzny kurz: ${[...kurzy].join(", ")}`);
console.log("  ok — lineárny kurz, bez bonusov za objem");

// Whitelist — čokoľvek mimo ponuky musí spadnúť, inak by si klient vypýtal
// faktúru na jednu hviezdu a dostal coiny za balík.
for (const zle of [0, -500, 1, 499, 501, 999, 7500, 1e9, Number.NaN]) {
  assert.equal(starPack(zle), null, `${zle} ⭐ nemal prejsť ako balík`);
}
assert.equal(starPack(500)?.coins, 6000);
console.log("  ok — mimo ponuky sa faktúra nevystaví");

// Odhad ceny pre používateľa je len orientačný, ale musí byť VYŠŠÍ než náš net —
// inak by sme klientovi ukazovali nezmysel.
for (const pack of STAR_PACKS) {
  assert.ok(
    approxUserCostUsd(pack.stars) > pack.stars * USD_PER_STAR,
    "cena pre používateľa musí byť vyššia než náš výnos",
  );
  assert.equal(pack.approxUsd, approxUserCostUsd(pack.stars));
}
assert.ok(APPROX_USD_PER_STAR_FOR_USER > USD_PER_STAR);
console.log("  ok — odhad ceny pre klienta dáva zmysel");

// Poplatok, ktorý klientovi UKAZUJEME. Keby raz vyšiel nula alebo záporný,
// tvrdili by sme mu, že Telegram je rovnako dobrý ako krypto — a to nie je.
{
  assert.ok(PLATFORM_FEE_PCT > 0 && PLATFORM_FEE_PCT < 100, "poplatok musí dávať zmysel");
  const pack = STAR_PACKS[0];
  const skutocny = (1 - pack.usd / pack.approxUsd) * 100;
  assert.ok(
    Math.abs(skutocny - PLATFORM_FEE_PCT) < 1,
    `ukazujeme ${PLATFORM_FEE_PCT} %, ale z balíka vychádza ${skutocny.toFixed(1)} %`,
  );
  console.log(`  ok — klientovi ukazujeme ${PLATFORM_FEE_PCT} % poplatok a sedí`);
}

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
for (const p of STAR_PACKS) {
  const krypto = p.approxUsd * COINS_PER_USD;
  console.log(
    `  ${String(p.stars).padStart(5)} ⭐ ≈ $${p.approxUsd.toFixed(2).padStart(6)} → ` +
      `${p.coins.toLocaleString("en-US").padStart(7)} coinov ` +
      `(nám ostane $${(p.stars * USD_PER_STAR).toFixed(2).padStart(6)}; ` +
      `za tie isté peniaze dá krypto ${krypto.toLocaleString("en-US")})`,
  );
}

console.log("\nstars-test: OK");

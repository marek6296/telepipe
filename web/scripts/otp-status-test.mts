/**
 * Mapovanie stavov OTP providerov.
 *
 * Existuje kvôli jednej konkrétnej chybe: slovo „received" znamená u VRNUM
 * „dorazil KÓD", ale u 5simu „dorazilo ČÍSLO a čaká sa na SMS". Kým sa mapovalo
 * bez ohľadu na providera, appka hlásila „Code received" s prázdnym poľom na kód
 * a klient čakal na niečo, čo nikdy neprišlo.
 *
 * Spustenie: npm run test:otp-status
 */
import assert from "node:assert/strict";

import { mapProviderStatus } from "../lib/otp-status.ts";

// TOTO je tá chyba. Keby sa sem raz vrátila, spadne to tu a nie u klienta.
assert.equal(
  mapProviderStatus("RECEIVED", false, "5sim"),
  "waiting",
  "5sim RECEIVED znamena cakame na SMS, nie kod dorazil",
);
assert.equal(
  mapProviderStatus("received", false, "vrnum"),
  "code_received",
  "u VRNUM received naozaj znamena kod",
);
console.log("  ok - slovo received sa vyklada podla providera");

// Kód je kód: keď ho máme, názvosloví providera nezáleží.
for (const provider of ["5sim", "vrnum", "cokolvek"]) {
  assert.equal(mapProviderStatus("PENDING", true, provider), "code_received");
}
console.log("  ok — s kódom je stav vždy code_received");

// Neznámy provider musí dostať bezpečný výklad, nie VRNUM legacy.
assert.equal(
  mapProviderStatus("received", false, "novy-provider"),
  "waiting",
  "neznamy provider nesmie dedit VRNUM vyklad slova received",
);
console.log("  ok - neznamy provider dostane bezpecny vyklad");

// Zvyšok slovníka 5simu.
const petsim: Array<[string, string]> = [
  ["PENDING", "provisioning"],
  ["RECEIVED", "waiting"],
  ["CANCELED", "cancelled"],
  ["TIMEOUT", "expired"],
  ["FINISHED", "completed"],
  ["BANNED", "failed"],
];
for (const [raw, expected] of petsim) {
  assert.equal(mapProviderStatus(raw, false, "5sim"), expected, `5sim ${raw}`);
}
console.log("  ok — celý slovník 5simu");

// Neznámy stav nesmie skončiť ako „kód dorazil" — to je jediný stav, ktorý
// klientovi sľubuje niečo konkrétne.
for (const provider of ["5sim", "vrnum", "novy"]) {
  assert.notEqual(mapProviderStatus("nieco_uplne_ine", false, provider), "code_received");
}
console.log("  ok — neznámy stav nikdy nesľúbi kód");

console.log("\notp-status-test: OK");

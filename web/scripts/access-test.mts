/**
 * Test pravidla odomknutia. Beží bez DB — `isUnlocked` je čistá funkcia
 * a práve preto sa dá takto lacno otestovať.
 *
 * Skutočný zámok je RLS v databáze; tento test stráži len to, aby sa web
 * s ňou nerozišiel.
 *
 * Spustenie: npm run test:access
 */
import assert from "node:assert/strict";

import { UNLOCKED_PLANS, isUnlocked } from "../lib/access.ts";
import { PLANS, PLAN_LABEL } from "../lib/admin-ui.ts";

const cases: Array<[string, { role: string; plan: string } | null, boolean]> = [
  ["free user je zamknutý", { role: "user", plan: "free" }, false],
  ["free_plus user je odomknutý", { role: "user", plan: "free_plus" }, true],
  ["vip_lite user je odomknutý", { role: "user", plan: "vip_lite" }, true],
  ["vip user je odomknutý", { role: "user", plan: "vip" }, true],
  ["admin je odomknutý aj na free", { role: "admin", plan: "free" }, true],
  ["superadmin je odomknutý aj na free", { role: "superadmin", plan: "free" }, true],
  ["neznámy plán je zamknutý", { role: "user", plan: "hacked" }, false],
  ["neznáma rola na free je zamknutá", { role: "root", plan: "free" }, false],
  ["chýbajúci účet je zamknutý", null, false],
];

for (const [name, account, expected] of cases) {
  assert.equal(isUnlocked(account), expected, name);
  console.log("  ok —", name);
}

// INVARIANT, ktorý by bol chytil `vip_lite`: každý plán okrem `free` musí byť
// odomknutý. Pribudnutie plánu bez zásahu do `UNLOCKED_PLANS` znamená klienta,
// ktorý má schválený účet a zároveň nemôže nič urobiť — a nič to nenahlási.
for (const plan of PLANS) {
  const odomknuty = UNLOCKED_PLANS.includes(plan);
  assert.equal(
    odomknuty,
    plan !== "free",
    plan === "free"
      ? "free musí ostať zamknutý"
      : `${plan} nie je v UNLOCKED_PLANS — klient by uviazol na /locked`,
  );
}
console.log("  ok — každý plán okrem free je odomknutý");

assert.ok(PLANS.includes("free_plus" as never), "free_plus musí byť v PLANS");
assert.equal(PLAN_LABEL.free_plus, "Standard+");
assert.equal(PLANS[PLANS.length - 1], "vip", "vip musí ostať posledný (ADMIN_ASSIGNABLE_PLANS ho odfiltrúva)");
console.log("  ok — PLANS a štítky");

console.log("access-test: OK");

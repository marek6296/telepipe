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

import { isUnlocked } from "../lib/access.ts";
import { PLANS, PLAN_LABEL } from "../lib/admin-ui.ts";

const cases: Array<[string, { role: string; plan: string } | null, boolean]> = [
  ["free user je zamknutý", { role: "user", plan: "free" }, false],
  ["free_plus user je odomknutý", { role: "user", plan: "free_plus" }, true],
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

assert.ok(PLANS.includes("free_plus" as never), "free_plus musí byť v PLANS");
assert.equal(PLAN_LABEL.free_plus, "Standard+");
assert.equal(PLANS[PLANS.length - 1], "vip", "vip musí ostať posledný (ADMIN_ASSIGNABLE_PLANS ho odfiltrúva)");
console.log("  ok — PLANS a štítky");

console.log("access-test: OK");

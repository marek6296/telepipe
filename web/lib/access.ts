// Relatívny import s príponou je tu zámerný, nie nedôslednosť: `@/` alias vie
// rozbaliť len Next, a tento modul musí ísť spustiť aj holým `node` v
// `scripts/access-test.mts` (rovnako ako `lib/coins.ts`).
import { asPlan, isAdminRole, type Plan } from "./admin-ui.ts";

/**
 * Odomknutie účtu — klientsky bezpečné zrkadlo DB funkcie `account_unlocked()`
 * (migrácia 20260819120000).
 *
 * POZOR: toto NIE JE hranica bezpečnosti. Skutočný zámok je RLS `with check`
 * na `models` INSERT. Táto funkcia existuje preto, aby appka vedela človeka
 * presmerovať skôr, než mu databáza vráti chybu — a aby sa to isté pravidlo
 * dalo použiť aj v client komponente (žiadny `next/headers` tu byť nesmie).
 *
 * Keď meníš pravidlo tu, MUSÍŠ ho zmeniť aj v `account_unlocked()`. Rozídenie
 * by neznamenalo rozbité UI, ale tichú dieru.
 */
export const UNLOCKED_PLANS: readonly Plan[] = ["free_plus", "vip"];

export type AccessAccount =
  | { role?: string | null; plan?: string | null }
  | null
  | undefined;

export function isUnlocked(account: AccessAccount): boolean {
  if (!account) return false;
  // Admin a superadmin sú odomknutí bez ohľadu na balík — inak by si Marek
  // zamkol sám seba tým, že si prepne plán.
  if (isAdminRole(account.role)) return true;
  // `asPlan` vracia „free" pre čokoľvek neznáme, takže neznámy plán = zamknuté.
  return UNLOCKED_PLANS.includes(asPlan(account.plan));
}

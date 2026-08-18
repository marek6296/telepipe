/**
 * Kredit a účtovanie LLM volaní z webu.
 *
 * Toto je webová dvojička `worker/src/credits.py` a matematika musí sedieť na
 * cent: cena z tabuľky `pricing` za milión tokenov, klientovi × `multiplier`,
 * chýbajúci cenník → fallback za Mtok. Keby web počítal inak než worker, ten
 * istý model by stál dve rôzne sumy podľa toho, kto ho zavolal.
 *
 * SERVER ONLY — `record_usage` beží cez service key (rola `authenticated` na
 * `pricing` ani na `usage_events` grant nemá a mať nebude: zápis do ledgeru je
 * vec servera, nie prehliadača).
 */

import { createClient, createServiceClient } from "@/lib/supabase/server";
import { toNumber } from "@/lib/format";
import {
  DEFAULT_MULTIPLIER,
  FALLBACK_PER_MTOK,
  computeCost,
  type PriceRow,
  type UsageCost,
} from "@/lib/pricing";

export type { PriceRow, UsageCost } from "@/lib/pricing";

export type CreditState = { balance: number; unlimited: boolean };

/**
 * Zostatok prihláseného účtu. `credit_state` RPC je len pre service_role
 * (migrácia 013), ale `authenticated` má select na `accounts` aj na stĺpec
 * `unlimited` — a RLS vráti výhradne vlastný riadok, takže user-scoped čítanie
 * je tu presnejšie než obchádzanie RLS service kľúčom.
 */
export async function creditState(): Promise<CreditState> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("accounts")
    .select("credit_balance_usd, unlimited")
    .maybeSingle();

  return {
    balance: toNumber(data?.credit_balance_usd as string | number | undefined),
    unlimited: Boolean(data?.unlimited),
  };
}

/**
 * Má účet na čo míňať? Pravidlo je to isté ako v `MeteredLlm._metered`:
 * neobmedzený účet sa nekontroluje, ostatným musí zostatok ostať kladný.
 */
export function hasCredit(state: CreditState): boolean {
  return state.unlimited || state.balance > 0;
}

export const OUT_OF_CREDITS_MSG =
  "You are out of credits. Top up your balance and the AI helper will work again.";

/**
 * Zápis spotreby do ledgeru. Nikdy nehádže — účtovanie nesmie zhodiť odpoveď,
 * ktorú klient už dostal (rovnaké pravidlo ako `MeteredLlm._bill`).
 */
export async function recordUsage(
  modelId: string,
  kind: "chat" | "summary" | "vision" | "audio" | "voice",
  slug: string,
  usage: { input: number; output: number },
): Promise<UsageCost | null> {
  const input = Math.max(0, Math.round(usage.input));
  const output = Math.max(0, Math.round(usage.output));
  // Volanie sa k modelu nedostalo (DNS, timeout pred odpoveďou) — nulový riadok
  // by ledger len zaplnil bez informácie.
  if (input <= 0 && output <= 0) return null;

  try {
    const supabase = createServiceClient();
    const price = await pricing(slug);
    const cost = computeCost(input, output, price, fallbackPerMtok());

    const { error } = await supabase.rpc("record_usage", {
      p_model: modelId,
      p_kind: kind,
      p_input_tokens: input,
      p_output_tokens: output,
      p_unit_count: 0,
      p_atlas_cost_usd: cost.atlas,
      p_charged_usd: cost.charged,
    });
    if (error) {
      console.error("record_usage failed", error.message);
      return null;
    }
    return cost;
  } catch (error) {
    console.error("record_usage failed", error);
    return null;
  }
}

/** Cenník pre slug, inak riadok `_default` — presne ako `Registry.pricing`. */
async function pricing(slug: string): Promise<PriceRow> {
  const supabase = createServiceClient();
  const { data } = await supabase
    .from("pricing")
    .select("model_slug, input_usd_per_mtok, output_usd_per_mtok, multiplier")
    .in("model_slug", [slug, "_default"]);

  const rows = data ?? [];
  const row = rows.find((item) => item.model_slug === slug) ?? rows.find((item) => item.model_slug === "_default");

  return {
    input_usd_per_mtok: toNumber(row?.input_usd_per_mtok as string | number | undefined),
    output_usd_per_mtok: toNumber(row?.output_usd_per_mtok as string | number | undefined),
    multiplier: row?.multiplier === undefined ? DEFAULT_MULTIPLIER : toNumber(row.multiplier),
  };
}

/** Prepísateľná fallback cena — worker číta tú istú premennú. */
function fallbackPerMtok(): number {
  const raw = Number(process.env.FALLBACK_PRICE_PER_MTOK);
  return Number.isFinite(raw) && raw > 0 ? raw : FALLBACK_PER_MTOK;
}

/**
 * Cena jedného LLM volania. Čistá matematika, žiadna databáza — aby sa dala
 * overiť testom a aby bolo na jednom mieste vidieť, že je to tá istá rovnica
 * ako `MeteredLlm._bill_inner` vo `worker/src/credits.py`:
 *
 *     atlas   = in/1e6 * input_usd_per_mtok + out/1e6 * output_usd_per_mtok
 *     charged = atlas * multiplier
 *
 * Chýbajúci cenník (obe ceny nulové, typicky riadok `_default`) padá na
 * `FALLBACK_PRICE_PER_MTOK` za súčet tokenov — presne ako worker.
 */

/** Rovnaký default ako `FALLBACK_PRICE_PER_MTOK` v `worker/src/config.py`. */
export const FALLBACK_PER_MTOK = 5.0;
/** Rovnaký default ako `price.get("multiplier", 2.0)` v `credits.py`. */
export const DEFAULT_MULTIPLIER = 2.0;

export type PriceRow = {
  input_usd_per_mtok: number;
  output_usd_per_mtok: number;
  multiplier: number;
};

export type UsageCost = { atlas: number; charged: number };

export function computeCost(
  input: number,
  output: number,
  price: PriceRow,
  fallbackPerMtok: number = FALLBACK_PER_MTOK,
): UsageCost {
  const hasPrice = price.input_usd_per_mtok > 0 || price.output_usd_per_mtok > 0;
  const atlas = hasPrice
    ? (input / 1e6) * price.input_usd_per_mtok + (output / 1e6) * price.output_usd_per_mtok
    : ((input + output) / 1e6) * fallbackPerMtok;
  const multiplier = price.multiplier > 0 ? price.multiplier : DEFAULT_MULTIPLIER;
  // Worker zapisuje `round(atlas, 6)` a `round(charged, 6)` — ledger musí mať
  // rovnaký počet desatinných miest, nech sa dajú riadky porovnávať.
  return { atlas: round6(atlas), charged: round6(atlas * multiplier) };
}

function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

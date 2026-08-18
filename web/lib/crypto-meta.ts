/**
 * Vizuál a kurzy pre platobné meny. Značka mince (farba + symbol) je to, čo
 * z monochrómneho zoznamu spraví niečo, na čo sa dá kliknúť bez rozmýšľania —
 * a `coingeckoId` je most k živému kurzu, aby sme vedeli povedať „pošli ≈ X".
 *
 * `cid` sedí na `PAY_CURRENCIES` v `lib/plisio.ts`. `symbol` je znak mince
 * (₿, ₮…) tam, kde existuje; inak sa v odznaku ukáže ticker. `stable` = mena
 * naviazaná na dolár, takže „koľko poslať" je prakticky rovná suma v USD.
 */

export type CryptoMeta = {
  ticker: string;
  color: string;
  /** Tmavý text v odznaku (žlté pozadie by biely text neuniesol). */
  darkText?: boolean;
  symbol?: string;
  coingeckoId: string;
  stable?: boolean;
};

export const CRYPTO_META: Record<string, CryptoMeta> = {
  USDT_TRX: { ticker: "USDT", color: "#26A17B", symbol: "₮", coingeckoId: "tether", stable: true },
  BTC: { ticker: "BTC", color: "#F7931A", symbol: "₿", coingeckoId: "bitcoin" },
  ETH: { ticker: "ETH", color: "#627EEA", symbol: "Ξ", coingeckoId: "ethereum" },
  SOL: { ticker: "SOL", color: "#9945FF", coingeckoId: "solana" },
  LTC: { ticker: "LTC", color: "#345D9D", symbol: "Ł", coingeckoId: "litecoin" },
  TRX: { ticker: "TRX", color: "#EF0027", coingeckoId: "tron" },
  BNB: { ticker: "BNB", color: "#F0B90B", darkText: true, coingeckoId: "binancecoin" },
  BCH: { ticker: "BCH", color: "#0AC18E", symbol: "₿", coingeckoId: "bitcoin-cash" },
};

export function cryptoMeta(cid: string): CryptoMeta {
  return CRYPTO_META[cid] ?? { ticker: cid, color: "#71717a", coingeckoId: "" };
}

/** Comma zoznam coingecko id-čiek pre jeden hromadný dopyt na kurzy. */
export function coingeckoIds(): string {
  return [...new Set(Object.values(CRYPTO_META).map((m) => m.coingeckoId).filter(Boolean))].join(",");
}

/**
 * Koľko mince poslať za dané USD. `null` = kurz nie je (dopyt zlyhal) alebo
 * mena nie je známa. Počet desatinných miest sa škáluje s cenou: drahá minca
 * (BTC) potrebuje viac miest než lacná (TRX).
 */
export function cryptoAmountForUsd(cid: string, usd: number, priceUsd: number | undefined): string | null {
  if (!priceUsd || priceUsd <= 0 || !Number.isFinite(usd) || usd <= 0) return null;
  const amount = usd / priceUsd;
  const decimals = amount >= 1000 ? 2 : amount >= 1 ? 4 : amount >= 0.01 ? 6 : 8;
  return amount.toLocaleString("en-US", { maximumFractionDigits: decimals });
}

export type CryptoRates = Record<string, number>;

/**
 * Živé USD kurzy pre všetky platobné meny (cid → cena za 1 mincu). Volá sa zo
 * SERVEROVEJ časti pri renderi Billing stránky, výsledok ide do panelu.
 *
 * Kurz je len ORIENTAČNÝ — kredit vždy počíta server z toho, čo naozaj príde na
 * adresu (Plisio). Preto zlyhanie dopytu nie je chyba: vráti sa prázdna mapa a
 * panel jednoducho neukáže „koľko poslať", zvyšok funguje. 60 s cache stačí,
 * kurz sa medzi dvoma dobitiami nepohne natoľko, aby to menilo rozhodnutie.
 */
export async function fetchCryptoRates(): Promise<CryptoRates> {
  const ids = coingeckoIds();
  if (!ids) return {};
  try {
    const response = await fetch(
      `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd`,
      { next: { revalidate: 60 }, signal: AbortSignal.timeout(6000) },
    );
    if (!response.ok) return {};
    const body = (await response.json()) as Record<string, { usd?: number }>;
    const rates: CryptoRates = {};
    for (const [cid, meta] of Object.entries(CRYPTO_META)) {
      const price = body[meta.coingeckoId]?.usd;
      if (price && price > 0) rates[cid] = price;
    }
    return rates;
  } catch {
    return {};
  }
}

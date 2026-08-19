import "server-only";

import { coinPriceFromUsdCost } from "@/lib/coins";
import { fiveSimApiToken, fiveSimPriceMultiplier } from "@/lib/env";
import { OTP_COUNTRIES, isKnownOtpCountry, isKnownOtpService, otpCountry } from "@/lib/otp-services";
import type { ProviderTelegramOrder, TelegramOtpCountry } from "@/lib/vrnum";

/**
 * 5sim — lacnejší zdroj Telegram OTP čísel.
 *
 * PREČO VZNIKOL: VRNUM predáva ten istý fond čísel s prirážkou 7–12×
 * (Kolumbia $1,21 vs $0,10 — a skladové zásoby sedia takmer na kus, čiže je to
 * preprodajca). Pri nákupke $0,10 prestáva byť nedoručená SMS finančný problém.
 *
 * DVA ROZDIELY OPROTI VRNUM, KTORÉ SA NEDAJÚ OBÍSŤ:
 *
 * 1. **Žiadny „resend".** 5sim nemá endpoint na opätovné poslanie SMS — má len
 *    „re-buy", čo je nový nákup za ďalšie peniaze. Tlačidlo Resend teda pri
 *    tomto providerovi nesmie nič sľubovať.
 *
 * 2. **Žiadna vlastná referencia.** VRNUM sme vedeli objednávku dohľadať podľa
 *    `clientReference`, keď nám vypadla sieť uprostred nákupu. 5sim pozná len
 *    svoje číselné id, ktoré sa dozvieme až z odpovede — takže keď odpoveď
 *    nedorazí, NEVIEME, či číslo vzniklo. Rieši sa to porovnaním zostatku pred
 *    a po (viď `buyActivation`), nie tichým zopakovaním requestu: opakovaný
 *    nákup by kúpil druhé číslo a zaplatil ho.
 *
 * RATING: 5sim penalizuje zrušenia (−0,1) aj timeouty (−0,15). Pri nule sa účet
 * na 24 h zamkne a NIKTO si nekúpi nič. Dobitie kreditu dáva +8. Preto sa
 * zostatok ratingu sleduje a hlási — viď `accountHealth`.
 */

const BASE = "https://5sim.net/v1";
const TIMEOUT_MS = 20_000;

export class FiveSimError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "FiveSimError";
    this.status = status;
  }
}

async function request<T>(path: string, auth = true): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE}${path}`, {
      headers: {
        Accept: "application/json",
        ...(auth ? { Authorization: `Bearer ${fiveSimApiToken()}` } : {}),
      },
      cache: "no-store",
      signal: controller.signal,
    });
    const text = await response.text();
    if (!response.ok) {
      // 5sim vracia chyby ako holý text („no free phones", „not enough user
      // balance"), nie ako JSON — preto sa číta text a nie .json().
      throw new FiveSimError(text.trim() || `5sim request failed (${response.status})`, response.status);
    }
    return (text ? JSON.parse(text) : {}) as T;
  } catch (error) {
    if (error instanceof FiveSimError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new FiveSimError("5sim did not answer in time");
    }
    throw new FiveSimError("5sim is temporarily unreachable");
  } finally {
    clearTimeout(timer);
  }
}

/* -------------------------------------------------------------------------- */
/*  Účet                                                                       */
/* -------------------------------------------------------------------------- */

export type FiveSimHealth = {
  balance: number;
  rating: number;
  /** Rating pod týmto číslom už treba riešiť — pri nule sa účet zamkne na 24 h
   *  a to znamená, že si NIKTO z klientov nekúpi číslo. */
  ratingLow: boolean;
};

export async function accountHealth(): Promise<FiveSimHealth> {
  const body = await request<{ balance: number; rating: number }>("/user/profile");
  const rating = Number(body.rating ?? 0);
  return {
    balance: Number(body.balance ?? 0),
    rating,
    ratingLow: rating < 20,
  };
}

/* -------------------------------------------------------------------------- */
/*  Cenník                                                                     */
/* -------------------------------------------------------------------------- */

/** Naša cena v coinoch. Rovnaké zaokrúhlenie ako pri VRNUM (násobok 50). */
export function telegramPriceCoins(providerPrice: number): number {
  return coinPriceFromUsdCost(providerPrice * fiveSimPriceMultiplier()).coins;
}

type GuestPrices = Record<string, Record<string, Record<string, { cost: number; count: number }>>>;

/**
 * Katalóg krajín. Cenník je VEREJNÝ (bez tokenu), takže sa dá čítať aj keď je
 * účet prázdny — a hlavne sa dá overiť nezávisle.
 */
export async function listCountries(service: string): Promise<TelegramOtpCountry[]> {
  const product = safeService(service);
  const body = await request<GuestPrices>(`/guest/prices?product=${product}`, false);
  const countries = body[product] ?? {};

  const out: TelegramOtpCountry[] = [];
  for (const [country, operators] of Object.entries(countries)) {
    // Len kurátorované krajiny. 5sim ich vracia 140+, ale číslo z Kamerunu si
    // nikto neobjedná a v zozname by len prekážalo.
    if (!isKnownOtpCountry(country)) continue;
    // Najlacnejší operátor, ktorý má čísla. Bez zásoby nemá zmysel ponúkať.
    let best: { cost: number; count: number } | null = null;
    for (const info of Object.values(operators)) {
      const cost = Number(info.cost);
      const count = Number(info.count);
      if (count <= 0 || !Number.isFinite(cost) || cost <= 0) continue;
      if (best === null || cost < best.cost) best = { cost, count };
    }
    if (!best) continue;

    const priceCredits = telegramPriceCoins(best.cost) / 1000;
    if (priceCredits <= 0) continue;

    const meta = otpCountry(country);
    out.push({
      code: country,
      name: meta?.name ?? prettyName(country),
      flag: meta?.flag ?? "",
      available: best.count,
      priceCredits,
    });
  }

  // Poradie ako v kurátorovanom zozname — cena tam nemá rozhodovať, USA má byť
  // prvá aj keď je drahšia.
  const poradie = new Map(OTP_COUNTRIES.map((c, i) => [c.id, i]));
  return out.sort((a, b) => (poradie.get(a.code) ?? 99) - (poradie.get(b.code) ?? 99));
}

export async function quote(
  service: string,
  countryCode: string,
): Promise<{ country: TelegramOtpCountry; providerPriceUsd: number } | null> {
  const product = safeService(service);
  const code = safeCountry(countryCode);
  const body = await request<GuestPrices>(
    `/guest/prices?country=${encodeURIComponent(code)}&product=${product}`,
    false,
  );
  const operators = body[code]?.[product] ?? {};

  let best: number | null = null;
  let count = 0;
  for (const info of Object.values(operators)) {
    const cost = Number(info.cost);
    const c = Number(info.count);
    if (c <= 0 || !Number.isFinite(cost) || cost <= 0) continue;
    if (best === null || cost < best) {
      best = cost;
      count = c;
    }
  }
  if (best === null) return null;

  const meta = otpCountry(code);
  return {
    providerPriceUsd: best,
    country: {
      code,
      name: meta?.name ?? prettyName(code),
      flag: meta?.flag ?? "",
      available: count,
      priceCredits: telegramPriceCoins(best) / 1000,
    },
  };
}

/* -------------------------------------------------------------------------- */
/*  Nákup a správa objednávky                                                  */
/* -------------------------------------------------------------------------- */

type BuyResponse = {
  id: number;
  phone: string;
  status: string;
  expires?: string;
  sms?: { code?: string; text?: string }[] | null;
};

/**
 * Kúpa čísla.
 *
 * `operator = any` necháva výber na 5sim — vyberie najlacnejší dostupný.
 *
 * POZOR: 5sim nepozná idempotency key. Opakovanie requestu po výpadku siete by
 * kúpilo DRUHÉ číslo a zaplatilo ho. Preto sa tu neopakuje NIKDY; volajúci má
 * pri neistote radšej porovnať zostatok cez `accountHealth()` a objednávku
 * dohľadať ručne.
 */
export async function buyActivation(
  service: string,
  countryCode: string,
): Promise<ProviderTelegramOrder> {
  const product = safeService(service);
  const country = encodeURIComponent(safeCountry(countryCode));
  const body = await request<BuyResponse>(`/user/buy/activation/${country}/any/${product}`);
  return toProviderOrder(body);
}

/**
 * Do URL na providera nesmie ísť nič, čo nie je v našom zozname. Bez tejto
 * kontroly by parameter z prehliadača určoval, čo sa nakupuje — a klient by si
 * mohol objednať službu, ktorú sme nikdy neocenili.
 */
function safeCountry(country: string): string {
  const id = (country || "").trim().toLowerCase();
  if (!isKnownOtpCountry(id)) {
    throw new FiveSimError(`Unsupported country: ${country}`);
  }
  return id;
}

function safeService(service: string): string {
  const id = (service || "").trim().toLowerCase();
  if (!isKnownOtpService(id)) {
    throw new FiveSimError(`Unsupported service: ${service}`);
  }
  return id;
}

export async function checkOrder(id: string): Promise<ProviderTelegramOrder> {
  return toProviderOrder(await request<BuyResponse>(`/user/check/${encodeURIComponent(id)}`));
}

/** Dokončiť — potvrdzuje, že kód dorazil a bol použitý. Dvíha rating (+0,5). */
export async function finishOrder(id: string): Promise<ProviderTelegramOrder> {
  return toProviderOrder(await request<BuyResponse>(`/user/finish/${encodeURIComponent(id)}`));
}

/** Zrušiť — používa sa, keď SMS nedorazí. Znižuje rating (−0,1). */
export async function cancelOrder(id: string): Promise<ProviderTelegramOrder> {
  return toProviderOrder(await request<BuyResponse>(`/user/cancel/${encodeURIComponent(id)}`));
}

function toProviderOrder(body: BuyResponse): ProviderTelegramOrder {
  const sms = Array.isArray(body.sms) ? body.sms : [];
  const code = sms.map((m) => m?.code).find((c) => typeof c === "string" && c) ?? null;
  return {
    id: String(body.id ?? ""),
    // 5sim vlastnú referenciu nepozná — viď komentár v hlavičke súboru.
    clientReference: "",
    phoneNumber: body.phone ? String(body.phone) : null,
    status: String(body.status ?? ""),
    code,
    expiresAt: body.expires ? String(body.expires) : null,
  };
}

/** 5sim stav → náš stav. `PENDING` je príprava, `RECEIVED` znamená „čakáme na SMS". */
export function mapStatus(status: string, hasCode: boolean): string {
  const s = (status || "").toUpperCase();
  if (hasCode) return "code_received";
  switch (s) {
    case "PENDING":
      return "provisioning";
    case "RECEIVED":
      return "waiting";
    case "FINISHED":
      return "completed";
    case "CANCELED":
      return "cancelled";
    case "TIMEOUT":
      return "expired";
    case "BANNED":
      return "failed";
    default:
      return "waiting";
  }
}

/** `unitedkingdom` → `United Kingdom`. 5sim vracia kľúče bez diakritiky a medzier. */
function prettyName(code: string): string {
  const known: Record<string, string> = {
    usa: "United States",
    unitedkingdom: "United Kingdom",
    easttimor: "East Timor",
    southafrica: "South Africa",
    saudiarabia: "Saudi Arabia",
    newzealand: "New Zealand",
    czech: "Czechia",
    sierraleone: "Sierra Leone",
    ivorycoast: "Ivory Coast",
    drcongo: "DR Congo",
    srilanka: "Sri Lanka",
  };
  if (known[code]) return known[code];
  return code.charAt(0).toUpperCase() + code.slice(1);
}

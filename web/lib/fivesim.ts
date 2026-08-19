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

/**
 * Pod touto úspešnosťou krajinu NEPONÚKAME.
 *
 * Dôvod je nameraný, nie odhadnutý. Pri Telegrame má 5sim krajiny s 0 %
 * (Nemecko, Francúzsko, Holandsko) a klient si pri nich kúpi číslo, ktoré
 * NIKDY nebude fungovať. Predať to za coiny — hoci ich vrátime — znamená
 * poslať človeka dvadsaťkrát skúšať niečo, čo nemá šancu vyjsť. Presne to sa
 * stalo pri prvom teste.
 *
 * Cena tu zámerne nerozhoduje. Refund funguje na oboch stranách (overené:
 * zostatok 5simu sa po zrušení vrátil na cent), takže drahšie číslo, ktoré
 * vyjde, je vždy lepšie než lacné, ktoré nevyjde.
 */
export const MIN_SUCCESS_RATE = 15;

/**
 * Krajina, ktorá sa ponúka VŽDY, keď má zásobu — aj keby jej úspešnosť dočasne
 * klesla pod prah. Je to najžiadanejšia destinácia a prázdny zoznam by bol
 * horší než zoznam s jednou položkou a poctivo napísaným percentom.
 */
const ALWAYS_OFFERED = "usa";

/** Naša cena v coinoch. Rovnaké zaokrúhlenie ako pri VRNUM (násobok 50). */
export function telegramPriceCoins(providerPrice: number): number {
  return coinPriceFromUsdCost(providerPrice * fiveSimPriceMultiplier()).coins;
}

type OperatorInfo = { cost: number; count: number; rate?: number };
type GuestPrices = Record<string, Record<string, Record<string, OperatorInfo>>>;

/** Operátor, ktorého naozaj kúpime — aj s jeho úspešnosťou. */
export type PickedOperator = {
  name: string;
  cost: number;
  count: number;
  /** Podiel aktivácií, ktoré u tohto operátora dopadli. `null` = 5sim ho neuvádza. */
  rate: number | null;
};

/**
 * Ktorého operátora kúpiť.
 *
 * ROZHODUJE ÚSPEŠNOSŤ, NIE CENA — a je to celý rozdiel medzi použiteľným a
 * nepoužiteľným číslom. Kým sa kupovalo cez `any` (teda najlacnejší), padli na
 * USA čísla od `virtual63` s 18 % úspešnosťou, prípadne `virtual28` s 8,7 %.
 * Klient vyskúšal dvadsať čísel a všetky boli zabanované alebo už registrované.
 * Ten istý deň mal `virtual51` za o 45 centov viac 42 % — viac než dvojnásobok.
 *
 * Cena rozhoduje až pri zhodnej úspešnosti. Ušetriť pol dolára na čísle, ktoré
 * v deviatich z desiatich prípadov nefunguje, nie je úspora.
 */
function pickOperator(operators: Record<string, OperatorInfo>): PickedOperator | null {
  let best: PickedOperator | null = null;
  for (const [name, info] of Object.entries(operators ?? {})) {
    const cost = Number(info?.cost);
    const count = Number(info?.count);
    if (!Number.isFinite(cost) || cost <= 0 || !(count > 0)) continue;
    const raw = Number(info?.rate);
    const rate = Number.isFinite(raw) ? raw : null;

    if (best === null) {
      best = { name, cost, count, rate };
      continue;
    }
    // Neznáma úspešnosť sa berie ako najhoršia — nechceme, aby operátor bez
    // údaja vyhral nad tým, o ktorom vieme, že funguje.
    const a = rate ?? -1;
    const b = best.rate ?? -1;
    if (a > b || (a === b && cost < best.cost)) best = { name, cost, count, rate };
  }
  return best;
}

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
    const best = pickOperator(operators);
    if (!best) continue;
    // Nepoužiteľné krajiny sa neukazujú vôbec. Klient nemá ako vedieť, že
    // „Nemecko 0 %" znamená vyhodené peniaze a stratený čas — my to vieme.
    const rate = best.rate ?? 0;
    // Nula nie je „nízka úspešnosť", je to nefunkčná destinácia — tam neplatí
    // ani výnimka pre USA. Ponúknuť číslo, ktoré preukázateľne nikdy nevyjde,
    // je horšie než tú krajinu neponúknuť vôbec.
    const usable = rate >= MIN_SUCCESS_RATE || (country === ALWAYS_OFFERED && rate > 0);
    if (!usable) continue;

    const priceCredits = telegramPriceCoins(best.cost) / 1000;
    if (priceCredits <= 0) continue;

    const meta = otpCountry(country);
    out.push({
      code: country,
      name: meta?.name ?? prettyName(country),
      flag: meta?.flag ?? "",
      available: best.count,
      priceCredits,
      successRate: best.rate,
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
): Promise<{
  country: TelegramOtpCountry;
  providerPriceUsd: number;
  /** Operátor, ktorý sa naozaj kúpi. Musí ísť až do `buyActivation`. */
  operator: string;
} | null> {
  const product = safeService(service);
  const code = safeCountry(countryCode);
  const body = await request<GuestPrices>(
    `/guest/prices?country=${encodeURIComponent(code)}&product=${product}`,
    false,
  );
  const operators = body[code]?.[product] ?? {};

  // TEN ISTÝ výber ako v `listCountries` a v `buyActivation` — inak by cena
  // v zozname patrila inému operátorovi než ten, ktorý sa naozaj kúpi.
  const best = pickOperator(operators);
  if (best === null) return null;

  const meta = otpCountry(code);
  return {
    providerPriceUsd: best.cost,
    operator: best.name,
    country: {
      code,
      name: meta?.name ?? prettyName(code),
      flag: meta?.flag ?? "",
      available: best.count,
      priceCredits: telegramPriceCoins(best.cost) / 1000,
      successRate: best.rate,
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
  const country = safeCountry(countryCode);

  // `any` znamená u 5simu „najlacnejší operátor" — a najlacnejší je vždy ten
  // najviac vypálený. Preto sa operátor vyberá vedome podľa úspešnosti (viď
  // `pickOperator`) a kupuje sa menovite. Keď sa výber nepodarí (výpadok
  // cenníka), padáme späť na `any`: horšie číslo je lepšie než žiadne.
  let operator = "any";
  try {
    const q = await quote(product, country);
    if (q?.operator) operator = q.operator;
  } catch {
    // Zámerne ticho — nákup nesmie spadnúť na tom, že sa nenačítal cenník.
  }

  const body = await request<BuyResponse>(
    `/user/buy/activation/${encodeURIComponent(country)}/${encodeURIComponent(operator)}/${product}`,
  );
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

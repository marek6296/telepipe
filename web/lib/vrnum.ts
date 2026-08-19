/** Server-only VRNUM integracia pre jednorazove Telegram OTP cisla. */

import { coinPriceFromUsdCost } from "@/lib/coins";
import { vrnumApiToken, vrnumOtpPriceMultiplier } from "@/lib/env";
import { toNumber } from "@/lib/format";
import { createServiceClient } from "@/lib/supabase/server";

const VRNUM_BASE_URL = "https://vrnum.com/api/v1";
const REQUEST_TIMEOUT_MS = 15_000;
const OTP_WINDOW_MS = 20 * 60_000;

export type TelegramOtpCountry = {
  code: string;
  name: string;
  flag: string;
  available: number;
  priceCredits: number;
};

export type TelegramOtpStatus =
  | "reserved"
  | "provisioning"
  | "waiting"
  | "code_received"
  | "completed"
  | "cancelled"
  | "expired"
  | "failed";

export type TelegramOtpOrder = {
  id: string;
  countryCode: string;
  countryName: string;
  countryFlag: string;
  phoneNumber: string | null;
  status: TelegramOtpStatus;
  providerStatus: string;
  otpCode: string | null;
  chargedCredits: number;
  refundedCredits: number;
  expiresAt: string | null;
  codeReceivedAt: string | null;
  cancelledAt: string | null;
  refundedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ProviderTelegramOrder = {
  id: string;
  clientReference: string;
  phoneNumber: string | null;
  status: string;
  code: string | null;
  expiresAt: string | null;
};

export type TelegramOtpDbOrder = {
  id: string;
  account_id: string | null;
  idempotency_key: string;
  /** Kto objednávku vybavil (migrácia 20260819210000). Staré riadky majú
   *  `vrnum`, nové `5sim` — identifikátory krajín aj objednávok sa líšia. */
  provider: string;
  /** Ktorá platforma sa overuje: telegram, whatsapp, instagram… */
  service: string;
  attempts_used: number;
  attempts_allowed: number;
  country_code: string;
  country_name: string;
  country_flag: string;
  phone_number: string | null;
  status: TelegramOtpStatus;
  provider_status: string;
  provider_order_id: string | null;
  client_reference: string;
  otp_code: string | null;
  charged_credits: string | number;
  refunded_credits: string | number;
  expires_at: string | null;
  code_received_at: string | null;
  cancelled_at: string | null;
  refunded_at: string | null;
  created_at: string;
  updated_at: string;
};

type VrnumErrorBody = { error?: { code?: string; message?: string } };

export class VrnumError extends Error {
  readonly status: number | null;
  readonly code: string;

  constructor(message: string, options?: { status?: number | null; code?: string }) {
    super(message);
    this.name = "VrnumError";
    this.status = options?.status ?? null;
    this.code = options?.code ?? "vrnum_error";
  }

  get isDefinitiveRejection(): boolean {
    return this.status !== null && this.status >= 400 && this.status < 500;
  }
}

/**
 * Nákupka + minimálne 50 %, potom najbližšia VYŠŠIA cena v násobku 50 coinov
 * (150, 1 150, 1 700 — nikdy 1 137). Zaokrúhlenie ide vždy nahor, takže
 * nemôže znížiť požadovanú maržu.
 *
 * Vracia USD, lebo to je jednotka zostatku aj stĺpca `charged_credits`;
 * klientovi sa všade zobrazujú coiny (`coins()` v `lib/coins.ts`).
 */
export function telegramOtpPrice(providerPrice: number): number {
  return coinPriceFromUsdCost(providerPrice * vrnumOtpPriceMultiplier()).usd;
}

/** Tá istá cena v coinoch — pre UI a kontrolu, že vyšiel násobok 50. */
export function telegramOtpPriceCoins(providerPrice: number): number {
  return coinPriceFromUsdCost(providerPrice * vrnumOtpPriceMultiplier()).coins;
}

export async function listTelegramCountries(): Promise<TelegramOtpCountry[]> {
  const body = await vrnumRequest<unknown>("/otp-catalog");

  return dataArray(body)
    .filter((item) => lower(item.service) === "telegram")
    .map((item) => {
      const providerPrice = number(item.price);
      return {
        code: lower(item.countryCode),
        name: text(item.countryName) || text(item.countryCode),
        flag: text(item.countryFlag),
        available: Math.max(0, Math.floor(number(item.available))),
        priceCredits: telegramOtpPrice(providerPrice),
      };
    })
    .filter((item) => item.code && item.name && item.priceCredits > 0)
    .sort((a, b) => {
      if (a.code === "usa") return -1;
      if (b.code === "usa") return 1;
      if ((a.available > 0) !== (b.available > 0)) return a.available > 0 ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
}

/** Cerstra serverova ponuka pouzita tesne pred rezervaciou kreditu. */
export async function telegramCountryQuote(countryCode: string): Promise<{
  country: TelegramOtpCountry;
  providerPriceUsd: number;
} | null> {
  const body = await vrnumRequest<unknown>("/otp-catalog");
  const item = dataArray(body).find(
    (row) => lower(row.service) === "telegram" && lower(row.countryCode) === countryCode,
  );
  if (!item) return null;
  const providerPriceUsd = number(item.price);
  if (providerPriceUsd <= 0) return null;
  return {
    providerPriceUsd,
    country: {
      code: lower(item.countryCode),
      name: text(item.countryName) || text(item.countryCode),
      flag: text(item.countryFlag),
      available: Math.max(0, Math.floor(number(item.available))),
      priceCredits: telegramOtpPrice(providerPriceUsd),
    },
  };
}

export async function purchaseTelegramNumber(input: {
  countryCode: string;
  clientReference: string;
  idempotencyKey: string;
}): Promise<ProviderTelegramOrder> {
  const body = await vrnumRequest<unknown>("/otp-numbers", {
    method: "POST",
    idempotencyKey: input.idempotencyKey,
    body: {
      service: "telegram",
      countryCode: input.countryCode,
      clientReference: input.clientReference,
    },
  });
  return providerOrder(body);
}

export async function getProviderTelegramOrder(id: string): Promise<ProviderTelegramOrder> {
  return providerOrder(
    await vrnumRequest<unknown>(`/otp-numbers/${encodeURIComponent(id)}`),
    id,
  );
}

export async function resendProviderTelegramCode(id: string): Promise<ProviderTelegramOrder> {
  return providerOrder(
    await vrnumRequest<unknown>(`/otp-numbers/${encodeURIComponent(id)}/resend`, {
      method: "POST",
    }),
    id,
  );
}

export async function cancelProviderTelegramOrder(id: string): Promise<ProviderTelegramOrder> {
  return providerOrder(
    await vrnumRequest<unknown>(`/otp-numbers/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
    id,
  );
}

/** Reconcile po timeout-e; list odpoved obsahuje nas clientReference. */
export async function findProviderOrder(
  clientReference: string,
): Promise<ProviderTelegramOrder | null> {
  const body = await vrnumRequest<unknown>("/otp-numbers?limit=100&offset=0");
  for (const item of dataArray(body)) {
    if (text(item.clientReference) === clientReference) {
      return providerOrder({ data: item });
    }
  }
  return null;
}

export async function listTelegramOtpOrders(accountId: string): Promise<TelegramOtpOrder[]> {
  const supabase = createServiceClient();
  const { data, error } = await supabase
    .from("telegram_otp_orders")
    .select(
      "id, account_id, idempotency_key, provider, service, attempts_used, attempts_allowed, country_code, country_name, country_flag, phone_number, status, provider_status, provider_order_id, client_reference, otp_code, charged_credits, refunded_credits, expires_at, code_received_at, cancelled_at, refunded_at, created_at, updated_at",
    )
    .eq("account_id", accountId)
    .order("created_at", { ascending: false })
    .limit(30);
  if (error) throw new Error(`Could not load Telegram OTP orders: ${error.message}`);
  return ((data ?? []) as unknown as TelegramOtpDbOrder[]).map(publicOrder);
}

export async function getDbOrder(
  accountId: string,
  orderId: string,
): Promise<TelegramOtpDbOrder | null> {
  const supabase = createServiceClient();
  const { data, error } = await supabase
    .from("telegram_otp_orders")
    .select("*")
    .eq("account_id", accountId)
    .eq("id", orderId)
    .maybeSingle();
  if (error) throw new Error(`Could not load Telegram OTP order: ${error.message}`);
  return data as unknown as TelegramOtpDbOrder | null;
}

export async function getDbOrderByIdempotency(
  accountId: string,
  idempotencyKey: string,
): Promise<TelegramOtpDbOrder | null> {
  const supabase = createServiceClient();
  const { data, error } = await supabase
    .from("telegram_otp_orders")
    .select("*")
    .eq("account_id", accountId)
    .eq("idempotency_key", idempotencyKey)
    .maybeSingle();
  if (error) throw new Error(`Could not load purchase retry: ${error.message}`);
  return data as unknown as TelegramOtpDbOrder | null;
}

export async function applyProviderOrder(
  orderId: string,
  provider: ProviderTelegramOrder,
): Promise<void> {
  const status = mapProviderStatus(provider.status, Boolean(provider.code));
  const now = new Date().toISOString();
  const supabase = createServiceClient();
  const { data: current } = await supabase
    .from("telegram_otp_orders")
    .select("expires_at")
    .eq("id", orderId)
    .maybeSingle();
  const update: Record<string, unknown> = {
    provider_order_id: provider.id,
    provider_status: provider.status,
    status,
    expires_at:
      provider.expiresAt ??
      current?.expires_at ??
      new Date(Date.now() + OTP_WINDOW_MS).toISOString(),
    updated_at: now,
  };
  if (provider.phoneNumber) update.phone_number = provider.phoneNumber;
  if (provider.code) {
    update.otp_code = provider.code;
    update.code_received_at = now;
  }
  if (status === "cancelled") update.cancelled_at = now;

  const { error } = await supabase.from("telegram_otp_orders").update(update).eq("id", orderId);
  if (error) throw new Error(`Could not save Telegram OTP status: ${error.message}`);
}

export function publicOrder(row: TelegramOtpDbOrder): TelegramOtpOrder {
  return {
    id: row.id,
    countryCode: row.country_code,
    countryName: row.country_name,
    countryFlag: row.country_flag,
    phoneNumber: row.phone_number,
    status: row.status,
    providerStatus: row.provider_status,
    otpCode: row.otp_code,
    chargedCredits: toNumber(row.charged_credits),
    refundedCredits: toNumber(row.refunded_credits),
    expiresAt: row.expires_at,
    codeReceivedAt: row.code_received_at,
    cancelledAt: row.cancelled_at,
    refundedAt: row.refunded_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export function mapProviderStatus(status: string, hasCode: boolean): TelegramOtpStatus {
  const value = status.trim().toLowerCase().replaceAll("-", "_");
  if (value.includes("cancel")) return "cancelled";
  if (value.includes("expire")) return "expired";
  if (value.includes("fail") || value.includes("error") || value.includes("reject")) {
    return "failed";
  }
  if (value.includes("complete") || value.includes("success")) return "completed";
  if (hasCode || value.includes("received")) return "code_received";
  if (value.includes("provision") || value.includes("pending")) return "provisioning";
  return "waiting";
}

async function vrnumRequest<T>(
  path: string,
  options?: {
    method?: "GET" | "POST";
    body?: Record<string, unknown>;
    idempotencyKey?: string;
  },
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${VRNUM_BASE_URL}${path}`, {
      method: options?.method ?? "GET",
      headers: {
        Authorization: `Bearer ${vrnumApiToken()}`,
        Accept: "application/json",
        ...(options?.body ? { "Content-Type": "application/json" } : {}),
        ...(options?.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
      },
      body: options?.body ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
    const body = (await response.json().catch(() => ({}))) as T & VrnumErrorBody;
    if (!response.ok) {
      throw new VrnumError(body.error?.message || `VRNUM request failed (${response.status})`, {
        status: response.status,
        code: body.error?.code,
      });
    }
    return body;
  } catch (error) {
    if (error instanceof VrnumError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new VrnumError("VRNUM did not confirm the request in time", { code: "timeout" });
    }
    throw new VrnumError("VRNUM is temporarily unreachable", { code: "network_error" });
  } finally {
    clearTimeout(timeout);
  }
}

function providerOrder(body: unknown, fallbackId = ""): ProviderTelegramOrder {
  const item = dataObject(body);
  const id = text(item.id) || text(item.orderId) || text(item.otpNumberId) || fallbackId;
  if (!id) {
    throw new VrnumError("VRNUM returned an order without an id", { code: "invalid_response" });
  }
  return {
    id,
    clientReference: text(item.clientReference),
    phoneNumber:
      nullableText(item.phoneNumber) ?? nullableText(item.number) ?? nullableText(item.phone),
    status: text(item.status) || "waiting",
    code:
      nullableText(item.code) ??
      nullableText(item.otp) ??
      nullableText(item.verificationCode) ??
      nullableText(item.smsCode),
    expiresAt: nullableText(item.expiresAt) ?? nullableText(item.expires_at),
  };
}

function dataObject(body: unknown): Record<string, unknown> {
  const root = record(body);
  return root.data && typeof root.data === "object" && !Array.isArray(root.data)
    ? record(root.data)
    : root;
}

function dataArray(body: unknown): Record<string, unknown>[] {
  const root = record(body);
  const data = root.data;
  if (Array.isArray(data)) return data.map(record);
  if (Array.isArray(body)) return body.map(record);
  return [];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown): string {
  if (typeof value === "string") return value.trim();
  return typeof value === "number" ? String(value) : "";
}

function nullableText(value: unknown): string | null {
  return text(value) || null;
}

function lower(value: unknown): string {
  return text(value).toLowerCase();
}

function number(value: unknown): number {
  return toNumber(value as string | number | null | undefined);
}

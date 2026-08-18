"use server";

import { randomUUID } from "node:crypto";

import { createServiceClient, getUser } from "@/lib/supabase/server";
import {
  VrnumError,
  applyProviderOrder,
  cancelProviderTelegramOrder,
  findProviderOrder,
  getDbOrder,
  getDbOrderByIdempotency,
  getProviderTelegramOrder,
  mapProviderStatus,
  publicOrder,
  purchaseTelegramNumber,
  resendProviderTelegramCode,
  telegramCountryQuote,
  type TelegramOtpDbOrder,
  type TelegramOtpOrder,
} from "@/lib/vrnum";

export type OtpActionResult =
  | { ok: true; order: TelegramOtpOrder; balance: number | null; message?: string }
  | { ok: false; error: string; retryable?: boolean; order?: TelegramOtpOrder };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function purchaseTelegramOtpAction(input: {
  countryCode: string;
  idempotencyKey: string;
}): Promise<OtpActionResult> {
  const account = await accountId();
  if (!account) return { ok: false, error: "Please sign in again." };

  const countryCode = input.countryCode.trim().toLowerCase();
  if (!countryCode || !UUID.test(input.idempotencyKey)) {
    return { ok: false, error: "Choose a country and try again." };
  }

  try {
    const existing = await getDbOrderByIdempotency(account, input.idempotencyKey);
    if (existing) {
      if (existing.country_code !== countryCode) {
        return { ok: false, error: "This purchase request was already used." };
      }
      if (!["reserved", "provisioning"].includes(existing.status)) {
        return { ok: true, order: publicOrder(existing), balance: await balance(account) };
      }
      return await provisionReservedOrder(existing);
    }

    const quote = await telegramCountryQuote(countryCode);
    if (!quote) return { ok: false, error: "That Telegram destination is no longer offered." };
    if (quote.country.available <= 0) {
      return { ok: false, error: `${quote.country.name} is temporarily sold out.` };
    }

    const orderId = randomUUID();
    const supabase = createServiceClient();
    const { data: reservedBalance, error } = await supabase.rpc(
      "reserve_telegram_otp_purchase",
      {
        p_order: orderId,
        p_account: account,
        p_idempotency: input.idempotencyKey,
        p_country_code: quote.country.code,
        p_country_name: quote.country.name,
        p_country_flag: quote.country.flag,
        p_provider_price: quote.providerPriceUsd,
        p_charged_credits: quote.country.priceCredits,
      },
    );
    if (error) {
      if (error.message.toLowerCase().includes("insufficient credits")) {
        return { ok: false, error: "You do not have enough Pipe Coins for this number." };
      }
      throw new Error(`Credit reservation failed: ${error.message}`);
    }

    await supabase
      .from("telegram_otp_orders")
      .update({ status: "provisioning", updated_at: new Date().toISOString() })
      .eq("id", orderId);

    const reserved = await getDbOrder(account, orderId);
    if (!reserved) throw new Error("Reserved OTP order was not found");
    const result = await provisionReservedOrder(reserved);
    return result.ok ? { ...result, balance: numeric(reservedBalance) } : result;
  } catch (error) {
    console.error("Telegram OTP purchase failed", safeError(error));
    return { ok: false, error: "The number could not be purchased right now. Please try again." };
  }
}

export async function refreshTelegramOtpAction(orderId: string): Promise<OtpActionResult> {
  const account = await accountId();
  if (!account || !UUID.test(orderId)) return { ok: false, error: "Order not found." };
  try {
    const row = await getDbOrder(account, orderId);
    if (!row) return { ok: false, error: "Order not found." };
    if (!row.provider_order_id) {
      const reconciled = await findProviderOrder(row.client_reference);
      if (!reconciled) {
        return {
          ok: true,
          order: publicOrder(row),
          balance: await balance(account),
          message: "Still confirming the number with the network.",
        };
      }
      await applyProviderOrder(row.id, reconciled);
      await refundIfProviderFailed(row, reconciled.status);
    } else {
      const provider = await getProviderTelegramOrder(row.provider_order_id);
      await applyProviderOrder(row.id, provider);
      await refundIfProviderFailed(row, provider.status);
    }
    return success(await requireDbOrder(account, orderId), await balance(account));
  } catch (error) {
    console.error("Telegram OTP refresh failed", safeError(error));
    return { ok: false, error: "Could not refresh the SMS yet. We will keep trying.", retryable: true };
  }
}

export async function resendTelegramOtpAction(orderId: string): Promise<OtpActionResult> {
  const account = await accountId();
  if (!account || !UUID.test(orderId)) return { ok: false, error: "Order not found." };
  try {
    const row = await requireDbOrder(account, orderId);
    if (!row.provider_order_id || !["waiting", "code_received"].includes(row.status)) {
      return { ok: false, error: "This number cannot request another SMS." };
    }
    const provider = await resendProviderTelegramCode(row.provider_order_id);
    await applyProviderOrder(row.id, provider);
    return success(await requireDbOrder(account, row.id), await balance(account), "Resend requested.");
  } catch (error) {
    console.error("Telegram OTP resend failed", safeError(error));
    const message = error instanceof VrnumError && error.isDefinitiveRejection
      ? "The network does not support resending for this number."
      : "Could not request another SMS yet.";
    return { ok: false, error: message };
  }
}

export async function cancelTelegramOtpAction(orderId: string): Promise<OtpActionResult> {
  const account = await accountId();
  if (!account || !UUID.test(orderId)) return { ok: false, error: "Order not found." };
  try {
    const row = await requireDbOrder(account, orderId);
    if (row.refunded_at) return success(row, await balance(account));
    if (!row.provider_order_id) {
      return {
        ok: false,
        error: "The purchase is still being confirmed. Refresh it before cancelling.",
        retryable: true,
      };
    }
    const provider = await cancelProviderTelegramOrder(row.provider_order_id);
    await applyProviderOrder(row.id, provider);
    const refundedBalance = await refund(row, "cancelled", "customer_cancelled");
    return success(
      await requireDbOrder(account, row.id),
      refundedBalance,
      "Number cancelled and Pipe Coins returned.",
    );
  } catch (error) {
    console.error("Telegram OTP cancel failed", safeError(error));
    return {
      ok: false,
      error: "Cancellation was not confirmed, so no coins were changed. Please try again.",
      retryable: true,
    };
  }
}

export async function completeTelegramOtpAction(orderId: string): Promise<OtpActionResult> {
  const account = await accountId();
  if (!account || !UUID.test(orderId)) return { ok: false, error: "Order not found." };
  try {
    const row = await requireDbOrder(account, orderId);
    if (!row.otp_code) return { ok: false, error: "The SMS code has not arrived yet." };
    const { error } = await createServiceClient()
      .from("telegram_otp_orders")
      .update({ status: "completed", updated_at: new Date().toISOString() })
      .eq("id", row.id)
      .eq("account_id", account);
    if (error) throw new Error(`Could not complete OTP order: ${error.message}`);
    return success(await requireDbOrder(account, row.id), await balance(account), "Activation completed.");
  } catch (error) {
    console.error("Telegram OTP completion failed", safeError(error));
    return { ok: false, error: "Could not finish this activation yet." };
  }
}

async function provisionReservedOrder(row: TelegramOtpDbOrder): Promise<OtpActionResult> {
  try {
    const provider = row.provider_order_id
      ? await getProviderTelegramOrder(row.provider_order_id)
      : await purchaseTelegramNumber({
          countryCode: row.country_code,
          clientReference: row.client_reference,
          idempotencyKey: row.idempotency_key,
        });
    await applyProviderOrder(row.id, provider);
    await refundIfProviderFailed(row, provider.status);
    return success(await requireDbOrder(row.account_id!, row.id), await balance(row.account_id!));
  } catch (error) {
    let reconciled = null;
    try {
      reconciled = await findProviderOrder(row.client_reference);
    } catch {
      // Ponechat povodnu chybu. Retry s rovnakym idempotency key je bezpecny.
    }
    if (reconciled) {
      await applyProviderOrder(row.id, reconciled);
      await refundIfProviderFailed(row, reconciled.status);
      return success(await requireDbOrder(row.account_id!, row.id), await balance(row.account_id!));
    }

    if (error instanceof VrnumError && error.isDefinitiveRejection) {
      await refund(row, "failed", error.code);
      return {
        ok: false,
        error: "The network rejected this purchase. Your Pipe Coins were returned.",
        order: publicOrder(await requireDbOrder(row.account_id!, row.id)),
        retryable: false,
      };
    }

    await createServiceClient()
      .from("telegram_otp_orders")
      .update({ last_error: "provider_confirmation_pending", updated_at: new Date().toISOString() })
      .eq("id", row.id);
    return {
      ok: false,
      error: "The network has not confirmed the purchase yet. Your request is safe to retry.",
      retryable: true,
      order: publicOrder(row),
    };
  }
}

async function refundIfProviderFailed(row: TelegramOtpDbOrder, providerStatus: string): Promise<void> {
  const mapped = mapProviderStatus(providerStatus, false);
  if (mapped === "cancelled" || mapped === "failed") {
    await refund(row, mapped, `provider_${mapped}`);
  }
}

async function refund(
  row: TelegramOtpDbOrder,
  status: "cancelled" | "failed",
  reason: string,
): Promise<number | null> {
  const { data, error } = await createServiceClient().rpc("refund_telegram_otp_purchase", {
    p_order: row.id,
    p_account: row.account_id!,
    p_status: status,
    p_reason: reason,
  });
  if (error) throw new Error(`Credit refund failed: ${error.message}`);
  return numeric(data);
}

async function requireDbOrder(account: string, orderId: string): Promise<TelegramOtpDbOrder> {
  const row = await getDbOrder(account, orderId);
  if (!row) throw new Error("Telegram OTP order not found");
  return row;
}

async function accountId(): Promise<string | null> {
  return (await getUser())?.id ?? null;
}

async function balance(account: string): Promise<number | null> {
  const { data, error } = await createServiceClient()
    .from("accounts")
    .select("credit_balance_usd")
    .eq("id", account)
    .maybeSingle();
  return error ? null : numeric(data?.credit_balance_usd);
}

function success(
  row: TelegramOtpDbOrder,
  currentBalance: number | null,
  message?: string,
): OtpActionResult {
  return { ok: true, order: publicOrder(row), balance: currentBalance, message };
}

function numeric(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function safeError(error: unknown): string {
  if (error instanceof VrnumError) return `${error.code}:${error.status ?? "network"}`;
  return error instanceof Error ? error.message : "unknown";
}

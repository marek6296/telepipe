import { NextResponse, type NextRequest } from "next/server";

import { telegramShopWebhookSecret } from "@/lib/env";
import { createServiceClient } from "@/lib/supabase/server";
import {
  answerPreCheckout,
  parsePayload,
  sendShopMessage,
} from "@/lib/telegram-shop";
import { notifyAdminNote } from "@/lib/telegram-admin";
import { starsCoinsForUsd } from "@/lib/stars";

export const dynamic = "force-dynamic";

/**
 * Webhook obchodného bota — platby za Pipe Coiny v Telegram Stars.
 *
 * Tri updaty, ktoré nás zaujímajú:
 *   pre_checkout_query  → musíme odpovedať do 10 s, inak Telegram platbu zruší
 *   successful_payment  → pripísať coiny
 *   refunded_payment    → odobrať ich späť
 *
 * Vraciame 200 aj pri odmietnutí: na non-200 Telegram doručovanie opakuje.
 */
export async function POST(request: NextRequest) {
  const secret = telegramShopWebhookSecret();
  if (secret && request.headers.get("x-telegram-bot-api-secret-token") !== secret) {
    return NextResponse.json({ ok: true });
  }

  let update: TelegramUpdate;
  try {
    update = (await request.json()) as TelegramUpdate;
  } catch {
    return NextResponse.json({ ok: true });
  }

  if (update.pre_checkout_query) {
    await handlePreCheckout(update.pre_checkout_query);
    return NextResponse.json({ ok: true });
  }

  const message = update.message;
  if (message?.successful_payment) {
    await handlePaid(message);
    return NextResponse.json({ ok: true });
  }
  if (message?.refunded_payment) {
    await handleRefund(message);
    return NextResponse.json({ ok: true });
  }

  // Ktokoľvek môže botovi napísať — je verejný. Nasmerujeme ho na web, kde si
  // nákup spustí; sám od seba tu nič kupovať nemá.
  if (message?.text && message.chat?.id) {
    await sendShopMessage(
      message.chat.id,
      "This bot only handles <b>Pipe Coin</b> top-ups.\n\n" +
        "Open <b>Billing</b> in your TelePipe dashboard and choose " +
        "<i>Pay with Telegram Stars</i> — the payment opens right here.",
    );
  }

  return NextResponse.json({ ok: true });
}

/**
 * Poslednou zastávkou pred stiahnutím peňazí. Payload overujeme TU, nie až po
 * platbe: keby bol pokazený, odmietnuť sa dá ešte bezbolestne. Po platbe už by
 * sme mali peniaze a nevedeli, komu ich pripísať.
 */
async function handlePreCheckout(query: PreCheckoutQuery): Promise<void> {
  const parsed = parsePayload(query.invoice_payload);
  if (!parsed) {
    await answerPreCheckout(query.id, false, "This invoice is no longer valid.");
    return;
  }

  const supabase = createServiceClient();
  const { data: account } = await supabase
    .from("accounts")
    .select("id")
    .eq("id", parsed.accountId)
    .maybeSingle();

  if (!account) {
    await answerPreCheckout(query.id, false, "That account no longer exists.");
    return;
  }
  await answerPreCheckout(query.id, true);
}

async function handlePaid(message: TelegramMessage): Promise<void> {
  const payment = message.successful_payment!;
  const parsed = parsePayload(payment.invoice_payload);
  const chatId = message.chat?.id;

  if (!parsed) {
    console.error("stars: zaplatené, ale payload sa nedá prečítať", payment.invoice_payload);
    await notifyAdminNote(
      "🚨 <b>Stars platba bez čitateľného payloadu</b>\n" +
        `charge: <code>${payment.telegram_payment_charge_id}</code>\n` +
        "Peniaze prišli, ale neviem, komu ich pripísať — treba to dohľadať ručne.",
    );
    return;
  }

  const coins = starsCoinsForUsd(parsed.usd);
  const supabase = createServiceClient();
  const { data, error } = await supabase.rpc("settle_star_payment", {
    p_charge_id: payment.telegram_payment_charge_id,
    p_account: parsed.accountId,
    p_tg_user: message.from?.id ?? null,
    p_stars: payment.total_amount,
    p_coins: coins,
    p_usd: parsed.usd,
    p_pack: "stars",
  });

  if (error) {
    console.error("settle_star_payment failed:", error.message);
    await notifyAdminNote(
      "🚨 <b>Stars platba sa nepripísala</b>\n" +
        `charge: <code>${payment.telegram_payment_charge_id}</code>\n` +
        `chyba: ${error.message}`,
    );
    return;
  }

  // `false` = tento charge_id sme už spracovali. Telegram doručuje opakovane,
  // takže to nie je chyba a klientovi sa druhýkrát neozveme.
  if (data === false) return;

  if (chatId) {
    await sendShopMessage(
      chatId,
      `✅ <b>${coins.toLocaleString("en-US")} Pipe Coins added.</b>\n\n` +
        "They're on your balance now — you can close this and go back to the dashboard.",
    );
  }
  await notifyAdminNote(
    `⭐ <b>Stars platba</b>: ${payment.total_amount} ⭐ → ` +
      `${coins.toLocaleString("en-US")} coinov ($${parsed.usd}).`,
  );
}

/**
 * Telegram dovoľuje používateľovi požiadať o vrátenie. Coiny musíme odobrať,
 * inak by stačilo minúť ich a potom refundovať — služba zadarmo.
 */
async function handleRefund(message: TelegramMessage): Promise<void> {
  const refund = message.refunded_payment!;
  const supabase = createServiceClient();
  const { data, error } = await supabase.rpc("refund_star_payment", {
    p_charge_id: refund.telegram_payment_charge_id,
  });

  if (error) {
    console.error("refund_star_payment failed:", error.message);
    return;
  }
  if (data === false) return; // už vrátené alebo neznáme

  await notifyAdminNote(
    `↩️ <b>Stars refund</b>: <code>${refund.telegram_payment_charge_id}</code>. ` +
      "Coiny som odobral — zostatok mohol ísť do mínusu.",
  );
}

/* -------------------------------------------------------------------------- */
/*  Tvary z Bot API — len to, čo naozaj čítame                                 */
/* -------------------------------------------------------------------------- */

type PreCheckoutQuery = {
  id: string;
  invoice_payload: string;
  total_amount: number;
  from?: { id: number };
};

type SuccessfulPayment = {
  telegram_payment_charge_id: string;
  invoice_payload: string;
  total_amount: number;
};

type TelegramMessage = {
  chat?: { id: number };
  from?: { id: number };
  text?: string;
  successful_payment?: SuccessfulPayment;
  refunded_payment?: { telegram_payment_charge_id: string; invoice_payload: string };
};

type TelegramUpdate = {
  message?: TelegramMessage;
  pre_checkout_query?: PreCheckoutQuery;
};

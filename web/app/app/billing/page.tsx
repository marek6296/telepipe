import type { Metadata } from "next";
import { Coins, MessageSquareText } from "lucide-react";

import { BillingMethods } from "@/components/app/billing-methods";
import { type CurrencyOption } from "@/components/app/billing-panel";
import { RelativeTime } from "@/components/app/relative-time";
import { telegramShopConfigured } from "@/lib/env";
import { Card, CardHeader, PageHeader, StatTile, TableWrap, Th } from "@/components/app/ui";
import {
  COINS_PER_REPLY,
  COIN_NAME_PLURAL,
  coins,
  estimatedReplies,
  toCoins,
} from "@/lib/coins";
import { fetchCryptoRates } from "@/lib/crypto-meta";
import { getAccount, requireUser } from "@/lib/models";
import { PAY_CURRENCIES, plisioEnabled } from "@/lib/plisio";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Billing",
};

const SUPPORT_EMAIL = "support@telepipe.app";

type HistoryRow = {
  payment_id: string;
  amount_usd: string | number;
  coins: string | number;
  pay_currency: string;
  status: string;
  credited: boolean;
  created_at: string;
  kind: "permanent" | "legacy";
};

/** Ľudský stav do histórie — `credited` má vždy posledné slovo. */
function statusLabel(row: HistoryRow): { text: string; tone: "ok" | "wait" | "bad" } {
  if (row.credited) return { text: "Completed", tone: "ok" };
  switch (row.status) {
    case "new":
      return { text: "Awaiting payment", tone: "wait" };
    case "pending":
    case "pending internal":
      return { text: "Confirming", tone: "wait" };
    case "mismatch":
      return { text: "Verifying amount", tone: "wait" };
    case "expired":
      return { text: "Expired", tone: "bad" };
    case "cancelled":
    case "cancelled duplicate":
      return { text: "Cancelled", tone: "bad" };
    case "error":
      return { text: "Failed", tone: "bad" };
    default:
      return { text: row.status, tone: "wait" };
  }
}

export default async function BillingPage() {
  await requireUser();
  const account = await getAccount();

  // Obe tabuľky sú RLS-scoped na prihlásený účet. Staré faktúrové riadky
  // ostávajú v histórii kvôli auditu, nové dobitia idú cez permanentné adresy.
  const supabase = await createClient();
  const [{ data: deposits }, { data: legacyPayments }, rates] = await Promise.all([
    supabase
      .from("crypto_deposit_events")
      .select("payment_id, source_usd, coins, pay_currency, status, credited, created_at")
      .order("created_at", { ascending: false })
      .limit(20),
    supabase
      .from("crypto_payments")
      .select("payment_id, usd, coins, pay_currency, status, credited, created_at")
      .order("created_at", { ascending: false })
      .limit(20),
    // Živé kurzy pre „koľko poslať". Zlyhanie = prázdna mapa, panel to znesie.
    fetchCryptoRates(),
  ]);

  const history: HistoryRow[] = [
    ...(deposits ?? []).map((row) => ({
      payment_id: String(row.payment_id),
      amount_usd: row.source_usd,
      coins: row.coins,
      pay_currency: String(row.pay_currency),
      status: String(row.status),
      credited: Boolean(row.credited),
      created_at: String(row.created_at),
      kind: "permanent" as const,
    })),
    ...(legacyPayments ?? []).map((row) => ({
      payment_id: String(row.payment_id),
      amount_usd: row.usd,
      coins: row.coins,
      pay_currency: String(row.pay_currency),
      status: String(row.status),
      credited: Boolean(row.credited),
      created_at: String(row.created_at),
      kind: "legacy" as const,
    })),
  ]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 20);

  const currencies: CurrencyOption[] = PAY_CURRENCIES.map((c) => ({ ...c }));
  const balanceCoins = toCoins(account?.credit_balance_usd);

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Billing"
        description="Top up Pipe Coins with crypto or straight from Telegram. Coins never expire and the balance updates itself."
      />

      {/* Dve dlaždice, nie tri. „Volume bonus" tu bol zavádzajúci: platí len
          pri krypte, nie pri Telegrame — a hore nad oboma metódami to tvrdil
          o všetkých. Presunul sa k tabu, ktorého sa naozaj týka. */}
      <div className="grid gap-4 sm:grid-cols-2">
        <StatTile
          label="Balance"
          value={coins(account?.credit_balance_usd)}
          hint={`${COIN_NAME_PLURAL} · they never expire`}
          icon={<Coins className="h-3.5 w-3.5" strokeWidth={1.75} />}
        />
        <StatTile
          label="Replies left (estimate)"
          value={estimatedReplies(balanceCoins).toLocaleString("en-US")}
          hint={`≈ ${COINS_PER_REPLY} coins per reply, all-in`}
          icon={<MessageSquareText className="h-3.5 w-3.5" strokeWidth={1.75} />}
        />
      </div>

      <div className="mt-4">
        <BillingMethods
          currencies={currencies}
          rates={rates}
          cryptoAvailable={plisioEnabled()}
          telegramAvailable={telegramShopConfigured()}
          telegramLinked={Boolean(account?.telegram_user_id)}
          supportEmail={SUPPORT_EMAIL}
        />
      </div>

      {history.length > 0 && (
        <Card className="mt-4">
          <CardHeader
            title="Payment history"
            description="Every confirmed deposit and its exact Pipe Coin credit."
          />
          <TableWrap minWidth="560px">
            <thead>
              <tr className="border-b border-[var(--app-border)]">
                <Th>Date</Th>
                <Th>Net value</Th>
                <Th align="right">Coins</Th>
                <Th>Paid with</Th>
                <Th align="right">Status</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--app-border)]">
              {history.map((row) => {
                const label = statusLabel(row);
                return (
                  <tr key={row.payment_id}>
                    <td className="px-5 py-3 text-[12.5px] text-[var(--app-text-3)]">
                      <RelativeTime iso={row.created_at} />
                    </td>
                    <td className="px-5 py-3 text-[12.5px] text-[var(--app-text)]">
                      ${Number(row.amount_usd).toFixed(2)}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums text-[12.5px] text-[var(--app-text)]">
                      {Number(row.coins).toLocaleString("en-US")}
                    </td>
                    <td className="px-5 py-3 text-[12.5px] text-[var(--app-text-2)]">
                      {row.pay_currency}
                    </td>
                    <td className="px-5 py-3 text-right text-[12.5px]">
                      <span
                        className={
                          label.tone === "ok"
                            ? "text-[#86efac]"
                            : label.tone === "bad"
                              ? "text-[#fca5a5]"
                              : "text-[var(--app-text-2)]"
                        }
                      >
                        {label.text}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
        </Card>
      )}
    </>
  );
}

import type { Metadata } from "next";
import { BadgeCheck, Coins, MessageSquareText, Percent, QrCode, Send } from "lucide-react";

import { BillingPanel, type CurrencyOption } from "@/components/app/billing-panel";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, CardHeader, PageHeader, StatTile, TableWrap, Th } from "@/components/app/ui";
import {
  COINS_PER_REPLY,
  COIN_NAME_PLURAL,
  coins,
  estimatedReplies,
  toCoins,
} from "@/lib/coins";
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

/** Jeden krok v páse „How it works" — symetrická tretina karty. */
function Step({
  icon,
  n,
  title,
  children,
}: {
  icon: React.ReactNode;
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="p-5">
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--app-border)] text-[var(--app-text-3)]">
          {icon}
        </span>
        <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--app-text-4)]">
          Step {n}
        </p>
      </div>
      <h3 className="mt-3 text-[13.5px] font-medium text-[var(--app-text)]">{title}</h3>
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--app-text-3)]">{children}</p>
    </div>
  );
}

export default async function BillingPage() {
  await requireUser();
  const account = await getAccount();

  // Obe tabuľky sú RLS-scoped na prihlásený účet. Staré faktúrové riadky
  // ostávajú v histórii kvôli auditu, nové dobitia idú cez permanentné adresy.
  const supabase = await createClient();
  const [{ data: deposits }, { data: legacyPayments }] = await Promise.all([
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
        description="Top up Pipe Coins with crypto. One permanent address per coin — send whenever you want, the balance updates itself."
      />

      <div className="grid gap-4 sm:grid-cols-3">
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
        <StatTile
          label="Volume bonus"
          value="+10% · +20%"
          hint="from $100 · from $250 per deposit"
          icon={<Percent className="h-3.5 w-3.5" strokeWidth={1.75} />}
        />
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Buy Pipe Coins"
          description="Choose an amount and currency, then reuse the same personal address for every future top-up."
          icon={<Coins className="h-4 w-4" strokeWidth={1.75} />}
        />
        <BillingPanel
          currencies={currencies}
          available={plisioEnabled()}
          supportEmail={SUPPORT_EMAIL}
        />
      </Card>

      <Card className="mt-4">
        <div className="grid divide-y divide-[var(--app-border)] md:grid-cols-3 md:divide-x md:divide-y-0">
          <Step icon={<QrCode className="h-3.5 w-3.5" strokeWidth={1.75} />} n={1} title="Choose amount and coin">
            Pick how much you want to add and which cryptocurrency you&apos;ll pay with. The
            estimate updates live, bonus included.
          </Step>
          <Step icon={<Send className="h-3.5 w-3.5" strokeWidth={1.75} />} n={2} title="Send to your permanent address">
            Every account gets its own address per coin. It never expires and never changes —
            save it and reuse it for every future top-up.
          </Step>
          <Step icon={<BadgeCheck className="h-3.5 w-3.5" strokeWidth={1.75} />} n={3} title="Coins land automatically">
            After network confirmations the net USD value converts to Pipe Coins, bonus applied.
            You can close the page — crediting continues on its own.
          </Step>
        </div>
        <div className="border-t border-[var(--app-border)] px-5 py-3.5 text-center text-[12px] leading-relaxed text-[var(--app-text-4)]">
          Sent a payment and don&apos;t see the coins after a few hours? Email{" "}
          <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>
            {SUPPORT_EMAIL}
          </a>{" "}
          — every payment is verifiable on the blockchain, nothing gets lost.
        </div>
      </Card>

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

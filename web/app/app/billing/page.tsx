import type { Metadata } from "next";
import { Coins, ShieldCheck } from "lucide-react";

import { BillingPanel, type CurrencyOption } from "@/components/app/billing-panel";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, CardHeader, PageHeader, TableWrap, Th } from "@/components/app/ui";
import { COIN_NAME_PLURAL, coins } from "@/lib/coins";
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

  // Both tables are RLS-scoped to the signed-in account. Legacy invoice rows
  // remain visible for audit even though all new top-ups use permanent pay-ins.
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

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Billing"
        description="Top up Pipe Coins with a permanent crypto address. Send whenever you want — no invoices, expiry, subscription, or package lock-in."
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
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

        <div className="space-y-4">
          <Card>
            <CardHeader title="Balance" />
            <div className="p-5">
              <p className="text-[28px] font-semibold leading-none tracking-[-0.03em] tabular-nums text-[var(--app-text)]">
                {coins(account?.credit_balance_usd)}
              </p>
              <p className="mt-2 text-[12px] text-[var(--app-text-3)]">
                {COIN_NAME_PLURAL} · they never expire
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="How it works"
              icon={<ShieldCheck className="h-4 w-4" strokeWidth={1.75} />}
            />
            <ol className="space-y-3 p-5 text-[12.5px] leading-relaxed text-[var(--app-text-3)]">
              <li>
                <strong className="text-[var(--app-text-2)]">1.</strong> Choose how much you want
                to add and select the cryptocurrency and network.
              </li>
              <li>
                <strong className="text-[var(--app-text-2)]">2.</strong> Send any amount to your
                permanent address. It stays the same and never expires.
              </li>
              <li>
                <strong className="text-[var(--app-text-2)]">3.</strong> Wait for network
                confirmations. The net USD value determines your coins and the larger-deposit
                bonus. You may close the page; crediting continues automatically.
              </li>
              <li className="border-t border-[var(--app-border)] pt-3 text-[var(--app-text-4)]">
                Sent a payment and don&apos;t see the coins after a few hours? Email{" "}
                <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>
                  {SUPPORT_EMAIL}
                </a>{" "}
                — every payment is verifiable on the blockchain, nothing gets lost.
              </li>
            </ol>
          </Card>
        </div>
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

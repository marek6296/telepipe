import type { Metadata } from "next";
import { Coins, ShieldCheck } from "lucide-react";

import { BillingPanel, type CurrencyOption, type PackOption } from "@/components/app/billing-panel";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, CardHeader, PageHeader, TableWrap, Th } from "@/components/app/ui";
import { COIN_NAME_PLURAL, COIN_PACKS, coins } from "@/lib/coins";
import { getAccount, requireUser } from "@/lib/models";
import { PAY_CURRENCIES, plisioEnabled } from "@/lib/plisio";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Billing",
};

const SUPPORT_EMAIL = "support@telepipe.app";

type PaymentRow = {
  payment_id: string;
  pack_id: string;
  usd: string | number;
  coins: string | number;
  pay_currency: string;
  status: string;
  credited: boolean;
  created_at: string;
};

/** Ľudský stav do histórie — `credited` má vždy posledné slovo. */
function statusLabel(row: PaymentRow): { text: string; tone: "ok" | "wait" | "bad" } {
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

export default async function BillingPage({
  searchParams,
}: {
  searchParams: Promise<{ pack?: string }>;
}) {
  await requireUser();
  const [account, params] = await Promise.all([getAccount(), searchParams]);

  // História cez RLS — klient vidí len vlastné platby a len povolené stĺpce.
  const supabase = await createClient();
  const { data: history } = await supabase
    .from("crypto_payments")
    .select("payment_id, pack_id, usd, coins, pay_currency, status, credited, created_at")
    .order("created_at", { ascending: false })
    .limit(20);

  const packs: PackOption[] = COIN_PACKS.map((pack) => ({
    id: pack.id,
    name: pack.name,
    priceUsd: pack.priceUsd,
    coins: pack.coins,
    bonusPct: pack.bonusPct,
    featured: pack.featured,
  }));
  const currencies: CurrencyOption[] = PAY_CURRENCIES.map((c) => ({ ...c }));

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Billing"
        description="Buy Pipe Coins with crypto. Pick a pack, send one transaction, and the balance updates itself — no subscription, coins never expire."
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader
            title="Buy Pipe Coins"
            description="Checkout happens right here — you'll get an address, the exact amount and a QR code."
            icon={<Coins className="h-4 w-4" strokeWidth={1.75} />}
          />
          <BillingPanel
            packs={packs}
            currencies={currencies}
            available={plisioEnabled()}
            initialPackId={params.pack}
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
                <strong className="text-[var(--app-text-2)]">1.</strong> Pick a pack and the coin
                you want to pay with.
              </li>
              <li>
                <strong className="text-[var(--app-text-2)]">2.</strong> Send{" "}
                <strong className="text-[var(--app-text-2)]">exactly</strong> the shown amount to
                the shown address — one transaction, right network.
              </li>
              <li>
                <strong className="text-[var(--app-text-2)]">3.</strong> Wait for network
                confirmations (usually minutes). You can close the page — coins are credited
                automatically, even if the confirmation lands hours later.
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

      {(history?.length ?? 0) > 0 && (
        <Card className="mt-4">
          <CardHeader
            title="Payment history"
            description="Your crypto top-ups. Completed means the coins are on your balance."
          />
          <TableWrap minWidth="560px">
            <thead>
              <tr className="border-b border-[var(--app-border)]">
                <Th>Date</Th>
                <Th>Pack</Th>
                <Th align="right">Coins</Th>
                <Th>Paid with</Th>
                <Th align="right">Status</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--app-border)]">
              {(history as PaymentRow[] | null)?.map((row) => {
                const label = statusLabel(row);
                return (
                  <tr key={row.payment_id}>
                    <td className="px-5 py-3 text-[12.5px] text-[var(--app-text-3)]">
                      <RelativeTime iso={row.created_at} />
                    </td>
                    <td className="px-5 py-3 text-[12.5px] text-[var(--app-text)]">
                      ${Number(row.usd)}
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

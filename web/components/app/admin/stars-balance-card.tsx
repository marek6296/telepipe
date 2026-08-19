import { Star } from "lucide-react";

import { Card, CardHeader } from "@/components/app/ui";
import { RelativeTime } from "@/components/app/relative-time";
import type { StarTransaction, StarsBalance } from "@/lib/stars-admin";
import { usd } from "@/lib/format";

/**
 * Kde presne ležia peniaze zo Stars.
 *
 * Existuje kvôli jednej otázke, ktorá je úplne namieste: „klienti platia, ale
 * kam tie peniaze idú?" Idú na Stars zostatok nášho bota — a toto je ten
 * zostatok, čítaný priamo z Telegramu, nie z našej databázy.
 */
export function StarsBalanceCard({
  balance,
  transactions,
}: {
  balance: StarsBalance;
  transactions: StarTransaction[];
}) {
  if (!balance.available) {
    return (
      <Card className="mt-4">
        <CardHeader
          title="Telegram Stars"
          description="Shop bot is not configured, so nothing can be collected yet."
          icon={<Star className="h-4 w-4" strokeWidth={1.75} />}
        />
      </Card>
    );
  }

  // Výber ide až od 1 000 ⭐ a až 21 dní po pripísaní — bez toho čísla je
  // zostatok len číslo a človek nevie, kedy sa k nemu dostane.
  const canWithdraw = balance.stars >= 1000;

  return (
    <Card className="mt-4">
      <CardHeader
        title="Telegram Stars"
        description="Collected on our shop bot. Withdrawn to TON through Fragment."
        icon={<Star className="h-4 w-4 text-[#fde047]" strokeWidth={1.75} />}
      />

      <div className="grid gap-px bg-[var(--app-border)] sm:grid-cols-3">
        <Tile label="Balance" value={`${balance.stars.toLocaleString("en-US")} ⭐`} />
        <Tile label="Worth roughly" value={usd(balance.approxUsd)} hint="before Fragment's ~5%" />
        <Tile
          label="Withdrawal"
          value={canWithdraw ? "Available" : `Needs 1,000 ⭐`}
          hint={canWithdraw ? "21 days after each payment" : `${(1000 - balance.stars).toLocaleString("en-US")} ⭐ to go`}
        />
      </div>

      {transactions.length > 0 && (
        <div className="border-t border-[var(--app-border)]">
          {transactions.map((tx) => (
            <div
              key={tx.id}
              className="flex items-center justify-between gap-3 border-b border-[var(--app-border)] px-5 py-2.5 text-[13px] last:border-b-0"
            >
              <span className="truncate text-[var(--app-text-2)]">{tx.who}</span>
              <span className="flex shrink-0 items-center gap-3">
                <span className="text-[11.5px] text-[var(--app-text-4)]">
                  <RelativeTime iso={tx.date} />
                </span>
                <span
                  className={
                    tx.direction === "incoming"
                      ? "tabular-nums text-[#86efac]"
                      : "tabular-nums text-[var(--app-text-3)]"
                  }
                >
                  {tx.direction === "incoming" ? "+" : "−"}
                  {tx.stars.toLocaleString("en-US")} ⭐
                </span>
              </span>
            </div>
          ))}
        </div>
      )}

      <p className="border-t border-[var(--app-border)] px-5 py-3 text-[12px] leading-relaxed text-[var(--app-text-4)]">
        Stars sit on the bot your Telegram account owns. To cash out, open{" "}
        <a
          href="https://fragment.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--app-text-2)] underline underline-offset-2"
        >
          fragment.com
        </a>
        , sign in with that same account and send them to a TON wallet — minimum
        1,000 ⭐, and each payment unlocks 21 days after it lands.
      </p>
    </Card>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-[var(--app-bg)] px-5 py-4">
      <p className="text-[11px] tracking-[0.14em] text-[var(--app-text-4)] uppercase">{label}</p>
      <p className="mt-1 text-[18px] text-[var(--app-text)] tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[11.5px] text-[var(--app-text-4)]">{hint}</p>}
    </div>
  );
}

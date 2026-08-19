"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bitcoin, Send, Star } from "lucide-react";

import { BillingPanel, type CurrencyOption } from "@/components/app/billing-panel";
import { TelegramStarsForm } from "@/components/app/telegram-stars-panel";
import type { CryptoRates } from "@/lib/crypto-meta";
import { cn } from "@/lib/utils";

type Method = "crypto" | "telegram";

/**
 * Výber platobnej metódy.
 *
 * Predtým tu boli dve karty pod sebou a človek musel scrollovať, aby zistil, že
 * existuje aj druhá možnosť — a „ako to funguje" popisovalo len tú prvú, hoci
 * viselo pod obidvomi. Teraz sa vyberá hore a dole je vždy postup k TEJ metóde,
 * ktorú si zvolil.
 */
export function BillingMethods({
  currencies,
  rates,
  cryptoAvailable,
  telegramAvailable,
  telegramLinked,
  supportEmail,
}: {
  currencies: CurrencyOption[];
  rates: CryptoRates;
  cryptoAvailable: boolean;
  telegramAvailable: boolean;
  telegramLinked: boolean;
  supportEmail: string;
}) {
  const [method, setMethod] = useState<Method>("crypto");

  // Keď je len jedna možnosť, prepínač je zbytočné bremeno.
  const both = cryptoAvailable && telegramAvailable;
  const active = telegramAvailable && !cryptoAvailable ? "telegram" : method;

  return (
    <div className="app-card overflow-hidden">
      {both && (
        <div className="grid grid-cols-2 border-b border-[var(--app-border)]">
          <MethodTab
            active={active === "crypto"}
            onClick={() => setMethod("crypto")}
            icon={<Bitcoin className="h-4 w-4" strokeWidth={1.75} />}
            title="Crypto"
            hint="Best rate · volume bonuses"
          />
          <MethodTab
            active={active === "telegram"}
            onClick={() => setMethod("telegram")}
            icon={<Star className="h-4 w-4" strokeWidth={1.75} />}
            title="Telegram"
            hint="No wallet needed"
          />
        </div>
      )}

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={active}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        >
          {active === "crypto" ? (
            <BillingPanel
              currencies={currencies}
              rates={rates}
              available={cryptoAvailable}
              supportEmail={supportEmail}
            />
          ) : (
            <div className="p-5">
              <TelegramStarsForm alreadyLinked={telegramLinked} />
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <Steps method={active} supportEmail={supportEmail} />
    </div>
  );
}

function MethodTab({
  active,
  onClick,
  icon,
  title,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "relative flex items-center gap-3 px-5 py-4 text-left transition-colors",
        active ? "bg-[var(--app-surface)]" : "hover:bg-[var(--app-surface-hover)]",
      )}
    >
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
          active
            ? "border-[var(--app-border-strong)] text-[var(--app-text)]"
            : "border-[var(--app-border)] text-[var(--app-text-4)]",
        )}
      >
        {icon}
      </span>
      <span className="min-w-0">
        <span
          className={cn(
            "block text-[13.5px]",
            active ? "font-medium text-[var(--app-text)]" : "text-[var(--app-text-2)]",
          )}
        >
          {title}
        </span>
        <span className="block truncate text-[11.5px] text-[var(--app-text-4)]">{hint}</span>
      </span>
      {active && <span className="absolute inset-x-0 -bottom-px h-px bg-[var(--app-text)]" />}
    </button>
  );
}

/** Tri kroky. Menia sa podľa metódy — spoločný text by pri jednej z nich klamal. */
function Steps({ method, supportEmail }: { method: Method; supportEmail: string }) {
  const steps =
    method === "crypto"
      ? [
          ["Pick an amount and a coin", "The estimate updates live, volume bonus included."],
          [
            "Send to your permanent address",
            "Every account has its own address per coin. It never expires — save it and reuse it.",
          ],
          [
            "Coins land on their own",
            "After network confirmations the balance updates. You can close the page.",
          ],
        ]
      : [
          ["Pick an amount", "You'll see the exact number of Stars before you pay."],
          [
            "Pay inside Telegram",
            "The button opens the payment sheet. No wallet, no exchange, no bot to start.",
          ],
          [
            "Coins land instantly",
            "Telegram confirms and the balance updates right away — usually before you switch back.",
          ],
        ];

  return (
    <div className="border-t border-[var(--app-border)]">
      <div className="grid divide-y divide-[var(--app-border)] md:grid-cols-3 md:divide-x md:divide-y-0">
        {steps.map(([title, body], index) => (
          <div key={title} className="px-5 py-4">
            <p className="text-[11px] tracking-[0.12em] text-[var(--app-text-4)] uppercase">
              Step {index + 1}
            </p>
            <h3 className="mt-2 text-[13px] font-medium text-[var(--app-text)]">{title}</h3>
            <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--app-text-3)]">{body}</p>
          </div>
        ))}
      </div>

      <p className="border-t border-[var(--app-border)] px-5 py-3 text-center text-[12px] text-[var(--app-text-4)]">
        {method === "crypto" ? (
          <>
            Paid but don&apos;t see the coins after a few hours? Email{" "}
            <a className="underline underline-offset-2" href={`mailto:${supportEmail}`}>
              {supportEmail}
            </a>{" "}
            — every payment is verifiable on the blockchain.
          </>
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <Send className="h-3 w-3" strokeWidth={1.75} />
            Costs more than crypto — Telegram and the app stores take a cut, and volume
            bonuses don&apos;t apply.
          </span>
        )}
      </p>
    </div>
  );
}

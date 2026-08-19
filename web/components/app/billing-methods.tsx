"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { BillingPanel, type CurrencyOption } from "@/components/app/billing-panel";
import { TelegramStarsForm } from "@/components/app/telegram-stars-panel";
import type { CryptoRates } from "@/lib/crypto-meta";
import { PLATFORM_FEE_PCT } from "@/lib/stars";
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
        <div className="border-b border-[var(--app-border)] p-4 sm:p-5">
          <p className="mb-3 text-[11px] tracking-[0.12em] text-[var(--app-text-4)] uppercase">
            Pay with
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <MethodCard
              active={active === "crypto"}
              onClick={() => setMethod("crypto")}
              brand={CRYPTO_BRAND}
              icon={<BitcoinGlyph />}
              title="Crypto"
              hint="No fees · volume bonuses"
            />
            <MethodCard
              active={active === "telegram"}
              onClick={() => setMethod("telegram")}
              brand={TELEGRAM_BRAND}
              icon={<TelegramGlyph />}
              title="Telegram"
              // Poplatok patrí SEM, na kartu voľby — nie až dnu. Človek sa
              // rozhoduje tu a musí vidieť, čím za pohodlie platí.
              hint={`No wallet · ~${PLATFORM_FEE_PCT}% fee`}
            />
          </div>
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
            <div className="p-4 sm:p-5">
              <TelegramStarsForm alreadyLinked={telegramLinked} brand={TELEGRAM_BRAND} />
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <Steps method={active} supportEmail={supportEmail} />
    </div>
  );
}

/* --------------------------------------------------------------------------
   Značkové farby. Sú tu natvrdo schválne: nejde o zoznam mincí, ale o dve
   platobné cesty, ktoré má človek na prvý pohľad rozoznať. Farba je jediné,
   čo z dvoch čiernych obdĺžnikov spraví voľbu.
-------------------------------------------------------------------------- */
const CRYPTO_BRAND = "#f7931a"; // Bitcoin orange
const TELEGRAM_BRAND = "#2aabee"; // Telegram blue

function BitcoinGlyph() {
  return <span className="text-[19px] font-bold leading-none text-white">₿</span>;
}

function TelegramGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-[19px] w-[19px]" fill="white" aria-hidden>
      <path d="M9.04 15.6 8.7 20.4c.5 0 .7-.2 1-.5l2.4-2.3 5 3.6c.9.5 1.6.2 1.8-.8l3.3-15.5c.3-1.3-.5-1.8-1.4-1.5L1.6 9.6c-1.3.5-1.3 1.2-.2 1.5l4.9 1.5L17.7 5.4c.5-.3 1-.2.6.2Z" />
    </svg>
  );
}

/**
 * Voľba platobnej metódy.
 *
 * Predtým to boli dva ploché nadpisy v čiernom páse a nevyzeralo to ako niečo,
 * na čo sa dá kliknúť. Teraz sú to karty so značkovou farbou a viditeľným
 * prepínačom — človek na prvý pohľad vidí, že má na výber.
 */
function MethodCard({
  active,
  onClick,
  brand,
  icon,
  title,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  brand: string;
  icon: React.ReactNode;
  title: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="radio"
      aria-checked={active}
      className={cn(
        "app-tap group relative flex items-center gap-3.5 rounded-xl border p-4 text-left transition-all",
        active
          ? "bg-[var(--app-surface)]"
          : "border-[var(--app-border)] hover:border-[var(--app-border-strong)] hover:bg-[var(--app-surface-hover)]",
      )}
      style={
        active
          ? { borderColor: brand, boxShadow: `0 0 0 1px ${brand}, 0 8px 28px -14px ${brand}` }
          : undefined
      }
    >
      <span
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-transform group-hover:scale-105"
        style={{ background: brand }}
      >
        {icon}
      </span>

      <span className="min-w-0 flex-1">
        <span className="block text-[14.5px] font-medium text-[var(--app-text)]">{title}</span>
        <span className="mt-0.5 block truncate text-[12px] text-[var(--app-text-4)]">{hint}</span>
      </span>

      {/* Prepínač napravo — bez neho by sa dalo prehliadnuť, ktorá je zvolená. */}
      <span
        className={cn(
          "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border transition-colors",
          active ? "border-transparent" : "border-[var(--app-border-strong)]",
        )}
        style={active ? { background: brand } : undefined}
      >
        {active && (
          <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none" aria-hidden>
            <path
              d="M2.5 6.2 4.8 8.5 9.5 3.8"
              stroke="#fff"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </span>
    </button>
  );
}

/** Tri kroky. Menia sa podľa metódy — spoločný text by pri jednej z nich klamal. */
function Steps({ method, supportEmail }: { method: Method; supportEmail: string }) {
  // Krátko. Kto platí, chce vedieť, čo ho čaká, nie čítať odstavce.
  const steps =
    method === "crypto"
      ? ["Pick an amount and a coin", "Send to your permanent address", "Coins land after confirmations"]
      : ["Pick a pack", "Pay inside Telegram", "Coins land instantly"];

  const accent = method === "crypto" ? CRYPTO_BRAND : TELEGRAM_BRAND;

  return (
    <div className="border-t border-[var(--app-border)]">
      <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:gap-6 sm:px-5">
        {steps.map((title, index) => (
          <div key={title} className="flex flex-1 items-center gap-2.5">
            <span
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11.5px] font-semibold tabular-nums"
              style={{ background: `${accent}22`, color: accent }}
            >
              {index + 1}
            </span>
            <span className="text-[12.5px] leading-snug text-[var(--app-text-2)]">{title}</span>
          </div>
        ))}
      </div>

      <p className="border-t border-[var(--app-border)] px-5 py-2.5 text-center text-[11.5px] text-[var(--app-text-4)]">
        {method === "crypto" ? (
          <>
            Coins missing after a few hours?{" "}
            {supportEmail ? (
              <a className="underline underline-offset-2" href={`mailto:${supportEmail}`}>
                {supportEmail}
              </a>
            ) : (
              // Chat v pravom dolnom rohu existuje a chodí priamo Marekovi —
              // je to lepší kontakt než e-mail, ktorý ešte nemá schránku.
              <>message us in the chat, bottom right</>
            )}
          </>
        ) : (
          <>
            About {PLATFORM_FEE_PCT}% of what you pay goes to Apple, Google and Telegram, so the
            same money buys fewer coins than crypto. No volume bonuses either.
          </>
        )}
      </p>
    </div>
  );
}

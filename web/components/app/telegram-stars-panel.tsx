"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink, Loader2 } from "lucide-react";

import { createStarInvoiceAction } from "@/app/app/billing/stars-actions";
import {
  STARS_MAX_USD,
  STARS_MIN_USD,
  STAR_OPTIONS,
  starsCoinsForUsd,
  starsForUsd,
} from "@/lib/stars";
import { cn } from "@/lib/utils";

/**
 * Formulár na nákup coinov cez Telegram Stars.
 *
 * Bez vlastnej hlavičky a rámu — sedí vnútri karty s prepínačom metód
 * (`billing-methods.tsx`), ktorá hlavičku aj postup rieši za neho.
 */
export function TelegramStarsForm({
  alreadyLinked,
  brand = "#2aabee",
}: {
  alreadyLinked: boolean;
  /** Značková farba Telegramu — nesie ju vybraná karta aj tlačidlo, nech je
   *  jasné, kam klik vedie. */
  brand?: string;
}) {
  const [usd, setUsd] = useState(10);
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sentToChat, setSentToChat] = useState(false);

  const amount = custom ? Math.round(Number(custom) || 0) : usd;
  const valid = amount >= STARS_MIN_USD && amount <= STARS_MAX_USD;
  const stars = valid ? starsForUsd(amount) : 0;
  const coins = valid ? starsCoinsForUsd(amount) : 0;

  async function pay() {
    setBusy(true);
    setError("");
    setSentToChat(false);

    const result = await createStarInvoiceAction(amount);
    setBusy(false);

    if (result.error) {
      setError(result.error);
      return;
    }
    if (result.sentToChat) setSentToChat(true);
    // Nový tab, nech klient nepríde o rozrobenú stránku.
    if (result.url) window.open(result.url, "_blank", "noopener,noreferrer");
  }

  return (
    <div>
      <p className="text-[11px] tracking-[0.12em] text-[var(--app-text-4)] uppercase">
        How much to top up
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {STAR_OPTIONS.map((option) => {
          const selected = !custom && usd === option.usd;
          return (
            <button
              key={option.usd}
              type="button"
              onClick={() => {
                setUsd(option.usd);
                setCustom("");
              }}
              className={cn(
                "app-tap rounded-xl border px-3 py-3 text-left transition-colors",
                selected
                  ? "bg-[var(--app-surface)]"
                  : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
              )}
              style={selected ? { borderColor: brand } : undefined}
            >
              <div className="text-[15px] text-[var(--app-text)] tabular-nums">
                {option.coins.toLocaleString("en-US")}
              </div>
              <div className="mt-0.5 text-[12px] text-[var(--app-text-4)] tabular-nums">
                {option.stars.toLocaleString("en-US")} ⭐
              </div>
            </button>
          );
        })}
      </div>

      <label className="mt-4 block">
        <span className="text-[12.5px] text-[var(--app-text-3)]">
          Or your own amount (${STARS_MIN_USD}–${STARS_MAX_USD})
        </span>
        <input
          type="number"
          inputMode="numeric"
          min={STARS_MIN_USD}
          max={STARS_MAX_USD}
          value={custom}
          onChange={(event) => setCustom(event.target.value)}
          placeholder={String(usd)}
          className="app-input mt-1.5 w-full"
        />
      </label>

      {error && (
        <p className="mt-3 text-[13px] text-[#fca5a5]" role="alert">
          {error}
        </p>
      )}
      {sentToChat && (
        <p className="mt-3 text-[13px] text-[#86efac]" role="status">
          Also sent to your Telegram — you can pay from the chat instead.
        </p>
      )}

      <button
        type="button"
        onClick={() => void pay()}
        disabled={busy || !valid}
        className="app-btn mt-4 w-full justify-center font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        style={{ background: brand, borderColor: brand }}
      >
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
        ) : valid ? (
          <motion.span key={stars} initial={{ opacity: 0.6 }} animate={{ opacity: 1 }} className="inline-flex items-center">
            Pay {stars.toLocaleString("en-US")} ⭐ for {coins.toLocaleString("en-US")} coins
            <ExternalLink className="ml-1.5 h-3.5 w-3.5" strokeWidth={1.75} />
          </motion.span>
        ) : (
          <>Choose an amount</>
        )}
      </button>

      <p className="mt-2 text-center text-[11.5px] text-[var(--app-text-4)]">
        {alreadyLinked
          ? "Opens Telegram — the invoice also lands in your chat."
          : "Opens Telegram — you don't need to start the bot first."}
      </p>
    </div>
  );
}

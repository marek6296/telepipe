"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink, Loader2, Star } from "lucide-react";

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
 * Platba cez Telegram Stars.
 *
 * Zámerne druhá voľba pod kryptom: Telegram si berie ~35 % (Apple/Google 30 %
 * + Telegram), takže je pre klienta drahšia a bonusy za objem tu neplatia.
 * Zmysel má tam, kde krypto nie je — klik a hotovo, bez peňaženky.
 */
export function TelegramStarsPanel({ alreadyLinked }: { alreadyLinked: boolean }) {
  const [usd, setUsd] = useState(10);
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sentToChat, setSentToChat] = useState(false);

  const amount = custom ? Math.round(Number(custom) || 0) : usd;
  const stars = amount >= STARS_MIN_USD ? starsForUsd(amount) : 0;
  const coins = amount >= STARS_MIN_USD ? starsCoinsForUsd(amount) : 0;

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
    // Odkaz otvára Telegram s platobným oknom. Nový tab, nech klient neprijde
    // o rozrobenú stránku.
    if (result.url) window.open(result.url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="app-panel p-6">
      <div className="flex items-center gap-2">
        <Star className="h-4 w-4 text-[#fde047]" strokeWidth={1.75} />
        <h2 className="text-[15px] font-medium text-[var(--app-text)]">Pay with Telegram</h2>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--app-text-3)]">
        No wallet, no exchange — pay with Telegram Stars in a couple of taps.
        Telegram and the app stores take a cut, so this costs more than crypto
        and volume bonuses don&apos;t apply.
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        {STAR_OPTIONS.map((option) => (
          <button
            key={option.usd}
            type="button"
            onClick={() => {
              setUsd(option.usd);
              setCustom("");
            }}
            className={cn(
              "app-tap rounded-lg border px-3.5 py-2 text-left transition-colors",
              !custom && usd === option.usd
                ? "border-[var(--app-text)] bg-[var(--app-surface)]"
                : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
            )}
          >
            <div className="text-[13.5px] text-[var(--app-text)]">
              {option.coins.toLocaleString("en-US")}
            </div>
            <div className="text-[11.5px] text-[var(--app-text-4)]">
              {option.stars.toLocaleString("en-US")} ⭐
            </div>
          </button>
        ))}
      </div>

      <label className="mt-4 block text-[12.5px] text-[var(--app-text-3)]">
        Or your own amount (${STARS_MIN_USD}–${STARS_MAX_USD})
        <input
          type="number"
          min={STARS_MIN_USD}
          max={STARS_MAX_USD}
          value={custom}
          onChange={(event) => setCustom(event.target.value)}
          placeholder={String(usd)}
          className="app-input mt-1.5 w-full"
        />
      </label>

      {stars > 0 && (
        <motion.p
          key={stars}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-3 text-[13px] text-[var(--app-text-2)]"
        >
          {coins.toLocaleString("en-US")} Pipe Coins for{" "}
          <span className="font-medium text-[var(--app-text)]">
            {stars.toLocaleString("en-US")} ⭐
          </span>
        </motion.p>
      )}

      {error && (
        <p className="mt-3 text-[13px] text-[#fca5a5]" role="alert">
          {error}
        </p>
      )}
      {sentToChat && (
        <p className="mt-3 text-[13px] text-[#86efac]" role="status">
          Sent to your Telegram — you can pay from the chat too.
        </p>
      )}

      <button
        type="button"
        onClick={() => void pay()}
        disabled={busy || stars === 0}
        className="app-btn app-btn-primary mt-4 w-full justify-center disabled:opacity-40"
      >
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
        ) : (
          <>
            Pay {stars > 0 ? `${stars.toLocaleString("en-US")} ⭐` : ""} in Telegram
            <ExternalLink className="ml-1.5 h-3.5 w-3.5" strokeWidth={1.75} />
          </>
        )}
      </button>

      <p className="mt-2.5 text-[11.5px] text-[var(--app-text-4)]">
        {alreadyLinked
          ? "The invoice also lands in your Telegram chat."
          : "Opens Telegram — you don't need to start the bot first."}
      </p>
    </div>
  );
}

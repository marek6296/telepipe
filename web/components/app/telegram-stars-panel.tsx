"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink, Loader2 } from "lucide-react";

import { createStarInvoiceAction } from "@/app/app/billing/stars-actions";
import { PLATFORM_FEE_PCT, STAR_PACKS, type StarPack } from "@/lib/stars";
import { cn } from "@/lib/utils";

/**
 * Formulár na nákup coinov cez Telegram Stars.
 *
 * Bez vlastnej hlavičky a rámu — sedí vnútri karty s prepínačom metód
 * (`billing-methods.tsx`), ktorá hlavičku aj postup rieši za neho.
 *
 * PREČO LEN PEVNÉ BALÍKY: hviezdy sa nedajú kúpiť po kuse. Keby si klient
 * navolil vlastnú sumu, faktúra by pýtala napríklad 410 ⭐, on by musel kúpiť
 * balík za 500 a 90 ⭐ by mu ostalo visieť. Balíky sú preto zhodné s tými,
 * ktoré predáva sám Telegram — kúpi presne toľko, koľko minie.
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
  const [pack, setPack] = useState<StarPack>(
    STAR_PACKS.find((p) => p.featured) ?? STAR_PACKS[0],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sentToChat, setSentToChat] = useState(false);

  async function pay() {
    setBusy(true);
    setError("");
    setSentToChat(false);

    const result = await createStarInvoiceAction(pack.stars);
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
        Choose a pack
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {STAR_PACKS.map((option) => {
          const selected = pack.stars === option.stars;
          return (
            <button
              key={option.stars}
              type="button"
              onClick={() => setPack(option)}
              aria-pressed={selected}
              className={cn(
                "app-tap rounded-xl border px-3 py-3 text-left transition-colors",
                selected
                  ? "bg-[var(--app-surface)]"
                  : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
              )}
              style={selected ? { borderColor: brand } : undefined}
            >
              <div className="text-[15px] text-[var(--app-text)] tabular-nums">
                {option.stars.toLocaleString("en-US")} ⭐
              </div>
              <div className="mt-0.5 text-[12px] text-[var(--app-text-3)] tabular-nums">
                ≈ ${option.approxUsd.toFixed(2)}
              </div>
              <div className="mt-1.5 text-[12px] text-[var(--app-text-4)] tabular-nums">
                {option.coins.toLocaleString("en-US")} coins
              </div>
            </button>
          );
        })}
      </div>

      {/* Klient inak nemá ako zistiť, že tá istá suma cez krypto kúpi viac —
          poplatok je celý mimo nás, ale mlčať o ňom by bolo neférové. */}
      <p className="mt-3 rounded-xl border border-[var(--app-border)] px-3 py-2.5 text-[12.5px] leading-relaxed text-[var(--app-text-3)]">
        <span className="text-[var(--app-text)]">≈ {PLATFORM_FEE_PCT} % goes to Apple, Google
        and Telegram</span> — that is their cut on every Stars purchase, not ours. Paying with
        crypto has no such fee: there, $1 always buys 1,000 coins.
      </p>

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
        disabled={busy}
        className="app-btn mt-4 w-full justify-center font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        style={{ background: brand, borderColor: brand }}
      >
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
        ) : (
          <motion.span
            key={pack.stars}
            initial={{ opacity: 0.6 }}
            animate={{ opacity: 1 }}
            className="inline-flex items-center"
          >
            Pay {pack.stars.toLocaleString("en-US")} ⭐ for{" "}
            {pack.coins.toLocaleString("en-US")} coins
            <ExternalLink className="ml-1.5 h-3.5 w-3.5" strokeWidth={1.75} />
          </motion.span>
        )}
      </button>

      <p className="mt-2 text-center text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        {alreadyLinked
          ? "Opens Telegram — the invoice also lands in your chat."
          : "Opens Telegram — you don't need to start the bot first."}{" "}
        Packs match the Stars bundles Telegram sells, so nothing is left over. VAT in your country
        may be added on top.
      </p>
    </div>
  );
}

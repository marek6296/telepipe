"use client";

import { useId, useState, useTransition } from "react";
import NumberFlow, { type Format } from "@number-flow/react";
import { motion, useReducedMotion } from "framer-motion";
import { Check, Loader2, Mail } from "lucide-react";

import { startTopUp, type TopUpResult } from "@/app/(marketing)/pricing/actions";
import {
  COINS_PER_REPLY,
  COIN_NAME_PLURAL,
  COIN_PACKS,
  coinsPerDollar,
  estimatedReplies,
  type CoinPack,
} from "@/lib/coins";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/*  Dáta                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Žiadne predplatné. Klient si kúpi Pipe Coiny a míňa ich, ako modelka pracuje.
 *
 * Balíky, kurz aj invariant ziskovosti žijú v `lib/coins.ts` — táto stránka ich
 * len kreslí. Keby sem niekto dopísal štvrtý balík rovno do JSX, obišiel by
 * `assertPacksProfitable` (a `npm run test:coins`), takže: pridávať výhradne
 * tam. `vip` sa tu nespomína ani slovom — je to interný balík pre kamarátov,
 * nie ponuka.
 */

/** Čo balík dostane navyše k samotným coinom — to isté pre všetky. */
const INCLUDED = [
  "Every model you want — no seat and no model limit",
  "Telegram agent replying from her own account",
  "Persona, long-term memory and human typing rhythm",
  "ElevenLabs voice notes, photo understanding, Fanvue agent",
  "Usage metered per model, per day, down to the coin",
];

type Unit = "coins" | "replies";

const PLAIN: Format = { maximumFractionDigits: 0 };

/* -------------------------------------------------------------------------- */
/*  Prepínač coiny / odpovede                                                  */
/* -------------------------------------------------------------------------- */

function UnitSwitch({ value, onChange }: { value: Unit; onChange: (next: Unit) => void }) {
  const layoutId = useId();
  const reduced = useReducedMotion();

  const options: { id: Unit; label: string }[] = [
    { id: "coins", label: COIN_NAME_PLURAL },
    { id: "replies", label: "Replies" },
  ];

  return (
    <div
      role="radiogroup"
      aria-label="Show pack size as"
      className="lp-switch mx-auto inline-flex items-center gap-1 rounded-full p-1"
    >
      {options.map((option) => {
        const active = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.id)}
            className={cn(
              "relative flex h-9 items-center gap-2 rounded-full px-4 text-[13px] font-medium transition-colors",
              active ? "text-[#0a0a0a]" : "text-white/55 hover:text-white",
            )}
          >
            {active && (
              // Kĺzavá pilulka — jeden element, `layoutId` ho prenesie medzi
              // oboma tlačidlami namiesto dvoch fade-ov.
              <motion.span
                layoutId={layoutId}
                aria-hidden
                className="absolute inset-0 rounded-full bg-[#fafafa]"
                transition={
                  reduced ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 36 }
                }
              />
            )}
            <span className="relative">{option.label}</span>
            {option.id === "replies" && (
              <span
                className={cn(
                  "relative rounded-full px-1.5 py-0.5 text-[10px] font-semibold tracking-[0.02em] transition-colors",
                  active ? "bg-black/10 text-[#0a0a0a]" : "bg-white/[0.07] text-white/60",
                )}
              >
                ≈{COINS_PER_REPLY} coins each
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Tlačidlo „kúpiť" — zatiaľ vedie na nás, nie do prázdna                     */
/* -------------------------------------------------------------------------- */

function TopUpButton({ pack, featured }: { pack: CoinPack; featured: boolean }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<TopUpResult | null>(null);

  // Kým platby nebežia, tlačidlo nesmie byť slepé: jedno kliknutie povie, čo
  // sa deje, a dá funkčnú cestu ďalej (mail). Keď pribudne Plisio, vetva
  // `redirect` prevezme kontrolu a UI sa nemení.
  const buy = () => {
    startTransition(async () => {
      const next = await startTopUp(pack.id);
      if (next.status === "redirect") {
        window.location.href = next.url;
        return;
      }
      setResult(next);
    });
  };

  if (result?.status === "unavailable") {
    return (
      <div className="mt-7">
        <a
          href={`mailto:${result.contactEmail}?subject=${encodeURIComponent(result.subject)}`}
          className={cn(
            "lp-btn h-11 w-full gap-2 text-[14px]",
            featured ? "lp-btn-primary" : "lp-btn-ghost",
          )}
        >
          <Mail className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          Email us to top up
        </a>
        <p className="mt-2.5 text-[12px] leading-relaxed text-white/35">
          Crypto checkout is being wired up right now. Until it lands we top you up by hand,
          usually the same day.
        </p>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={buy}
      disabled={pending}
      aria-label={`Buy the ${pack.name} pack — ${pack.coins.toLocaleString("en-US")} ${COIN_NAME_PLURAL} for $${pack.priceUsd}`}
      className={cn(
        "lp-btn mt-7 h-11 w-full gap-2 text-[14px]",
        featured ? "lp-btn-primary" : "lp-btn-ghost",
        pending && "opacity-70",
      )}
    >
      {pending && <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden />}
      Buy {pack.coins.toLocaleString("en-US")} coins
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Cenník                                                                     */
/* -------------------------------------------------------------------------- */

export function PricingTable() {
  const [unit, setUnit] = useState<Unit>("coins");
  const showReplies = unit === "replies";

  return (
    <div>
      <div className="flex justify-center">
        <UnitSwitch value={unit} onChange={setUnit} />
      </div>

      <div className="mt-12 grid gap-4 lg:grid-cols-3">
        {COIN_PACKS.map((pack) => {
          const headline = showReplies ? estimatedReplies(pack.coins) : pack.coins;
          const perDollar = coinsPerDollar(pack);

          return (
            <article
              key={pack.id}
              className={cn(
                "relative flex flex-col overflow-hidden rounded-[20px] p-7",
                pack.featured ? "lp-plan-featured" : "lp-card",
              )}
            >
              {pack.featured && (
                <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
              )}
              {pack.bonusPct > 0 && (
                <span className="lp-hairline absolute right-6 top-7 rounded-full bg-white/[0.06] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/70">
                  +{pack.bonusPct}% free
                </span>
              )}

              <div className="relative">
                <h2 className="text-[17px] font-semibold text-white">{pack.name}</h2>
                <p className="mt-2 min-h-[42px] max-w-[26ch] text-[13.5px] leading-relaxed text-white/40">
                  {pack.tagline}
                </p>

                <div className="mt-7 flex items-end gap-2">
                  <NumberFlow
                    value={headline}
                    format={PLAIN}
                    // `willChange` drží číslice na vlastnej vrstve počas rolovania
                    willChange
                    className="lp-tight text-[clamp(2.2rem,4vw,2.9rem)] font-semibold leading-none text-white tabular-nums"
                  />
                  <span className="pb-1 text-[13px] text-white/35">
                    {showReplies ? "replies" : COIN_NAME_PLURAL}
                  </span>
                </div>

                <p className="mt-2.5 h-4 text-[12px] text-white/30">
                  ${pack.priceUsd} one-off · {perDollar.toLocaleString("en-US")} coins per dollar
                </p>

                <TopUpButton pack={pack} featured={Boolean(pack.featured)} />
              </div>

              <div className="relative mt-8 border-t border-white/[0.07] pt-7">
                <p className="mb-4 text-[12.5px] font-medium text-white/55">
                  Every pack includes
                </p>
                <ul className="space-y-3">
                  {INCLUDED.map((feature) => (
                    <li key={feature} className="flex gap-3">
                      <Check
                        className="mt-[3px] h-3.5 w-3.5 shrink-0 text-white/45"
                        strokeWidth={2}
                        aria-hidden
                      />
                      <span className="text-[13.5px] leading-relaxed text-white/55">
                        {feature}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </article>
          );
        })}
      </div>

      <p className="mt-10 text-center text-[12.5px] leading-relaxed text-white/30">
        There is no subscription and nothing renews. You buy Pipe Coins once, and they come off
        the balance as she works — every reply, transcription and voice second metered per model.
        Reply estimates use {COINS_PER_REPLY} coins per reply: a rounded-up, all-in figure measured
        from a real week of live traffic, memory work included. Long conversations cost a little
        more, short ones less.
      </p>
    </div>
  );
}

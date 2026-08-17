import { Check, Mic, Sparkles, Zap } from "lucide-react";

import { cn } from "@/lib/utils";

// Kruh progress ringu — polomer 38 ⇒ obvod 238.76
export const RING_RADIUS = 38;
export const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
/** Koľko z ringu je vyplnené (72 % zo 297 chatov = 214 konverzií). */
export const RING_PROGRESS = 0.72;
export const RING_TARGET = 214;

/**
 * iPhone mockup s reklamným príbehom: Telegram konverzácia, zlatý ring counter
 * „Fans converted" a Fanvue widgety.
 *
 * `animated` = GSAP si prevezme počiatočné stavy (elementy sú preto skryté
 * inline štýlom). Statická verzia pre `prefers-reduced-motion` renderuje rovnaký
 * obsah rovno v cieľovom stave.
 */
export function PhoneMockup({
  animated = false,
  className,
}: {
  animated?: boolean;
  className?: string;
}) {
  // Pri animovanej verzii štartujú prvky skryté — GSAP ich vyvolá na scrolle
  const hidden = animated ? { opacity: 0 } : undefined;
  const ringDash = animated
    ? RING_CIRCUMFERENCE
    : RING_CIRCUMFERENCE * (1 - RING_PROGRESS);

  return (
    <div
      data-phone
      className={cn(
        "relative h-[560px] w-[276px] shrink-0 rounded-[46px] p-[3px]",
        "bg-[linear-gradient(160deg,#4a4a4a_0%,#151515_38%,#000_62%,#3a3a3a_100%)]",
        "shadow-[0_50px_90px_-20px_rgba(0,0,0,0.9),0_0_0_1px_rgba(212,175,55,0.16),inset_0_1px_0_rgba(255,255,255,0.16)]",
        className,
      )}
      style={{ transformStyle: "preserve-3d" }}
    >
      {/* Bočné tlačidlá */}
      <span className="absolute -left-[3px] top-[128px] h-11 w-[3px] rounded-l bg-neutral-700" />
      <span className="absolute -left-[3px] top-[186px] h-11 w-[3px] rounded-l bg-neutral-700" />
      <span className="absolute -right-[3px] top-[160px] h-16 w-[3px] rounded-r bg-neutral-700" />

      {/* Displej */}
      <div className="relative h-full w-full overflow-hidden rounded-[43px] bg-[linear-gradient(180deg,#0d0d0f_0%,#050505_100%)]">
        {/* Dynamic island */}
        <div className="absolute left-1/2 top-2.5 z-30 h-[26px] w-[86px] -translate-x-1/2 rounded-full bg-black shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]" />

        {/* Status bar */}
        <div className="flex items-center justify-between px-6 pt-3.5 text-[10px] font-medium text-white/60">
          <span>9:41</span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-[7px] w-[7px] rounded-full bg-[var(--gold)]" />
            5G
          </span>
        </div>

        {/* Hlavička chatu */}
        <div className="mt-3 flex items-center gap-2.5 border-b border-white/[0.06] px-4 pb-3">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-full bg-[linear-gradient(140deg,#e8c766,#a8872a)] text-[13px] font-bold text-black">
            L
            <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[#0a0a0c] bg-emerald-400" />
          </div>
          <div className="min-w-0 leading-tight">
            <p className="truncate text-[12.5px] font-semibold text-white">Lena</p>
            <p className="text-[10px] text-emerald-400/90">online · replying</p>
          </div>
          <span className="ml-auto rounded-full bg-[rgba(212,175,55,0.12)] px-2 py-0.5 text-[8.5px] font-semibold tracking-wide text-[var(--gold-light)]">
            AI
          </span>
        </div>

        {/* Konverzácia */}
        <div className="space-y-2 px-3.5 py-3">
          <div data-bubble="in" style={hidden} className="flex justify-start">
            <div className="max-w-[78%] rounded-2xl rounded-bl-md bg-white/[0.07] px-3 py-2 text-[11px] leading-snug text-white/85">
              hey gorgeous, you up? 😏
              <span className="ml-2 text-[8.5px] text-white/35">02:14</span>
            </div>
          </div>

          <div data-bubble="out" style={hidden} className="flex justify-end">
            <div className="max-w-[80%] rounded-2xl rounded-br-md bg-[linear-gradient(150deg,#e8c766,#c9a233)] px-3 py-2 text-[11px] leading-snug text-black/90 shadow-[0_6px_18px_rgba(212,175,55,0.28)]">
              always up for you 😘 wanna hear something?
              <span className="ml-1.5 inline-flex items-center gap-0.5 text-[8.5px] text-black/45">
                02:14 <Check className="h-2.5 w-2.5" strokeWidth={3} />
              </span>
            </div>
          </div>

          {/* Hlasovka */}
          <div data-bubble="voice" style={hidden} className="flex justify-end">
            <div className="flex max-w-[80%] items-center gap-2 rounded-2xl rounded-br-md bg-[linear-gradient(150deg,#e8c766,#c9a233)] px-3 py-2 shadow-[0_6px_18px_rgba(212,175,55,0.28)]">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-black/20">
                <Mic className="h-3 w-3 text-black/80" />
              </span>
              <span className="flex items-end gap-[2px]" aria-hidden>
                {[6, 11, 7, 14, 9, 16, 8, 12, 5, 10, 7, 13, 6].map((h, i) => (
                  <span
                    key={i}
                    className="w-[2px] rounded-full bg-black/45"
                    style={{ height: `${h}px` }}
                  />
                ))}
              </span>
              <span className="text-[9.5px] font-semibold text-black/70">0:12</span>
            </div>
          </div>

          <div data-bubble="in" style={hidden} className="flex justify-start">
            <div className="max-w-[78%] rounded-2xl rounded-bl-md bg-white/[0.07] px-3 py-2 text-[11px] leading-snug text-white/85">
              omg your voice 🔥 where can I see more?
            </div>
          </div>

          <div data-bubble="link" style={hidden} className="flex justify-end">
            <div className="max-w-[82%] rounded-2xl rounded-br-md bg-[linear-gradient(150deg,#e8c766,#c9a233)] px-3 py-2 text-[11px] leading-snug text-black/90 shadow-[0_6px_18px_rgba(212,175,55,0.28)]">
              everything is here, baby 💋
              <span className="mt-1 block truncate rounded-lg bg-black/15 px-2 py-1 text-[10px] font-semibold underline decoration-black/30">
                fanvue.com/lena
              </span>
            </div>
          </div>
        </div>

        {/* Spodný panel — ring counter + widgety */}
        <div className="absolute inset-x-0 bottom-0 rounded-t-3xl border-t border-[rgba(212,175,55,0.16)] bg-[linear-gradient(180deg,rgba(18,18,18,0.94),rgba(4,4,4,0.98))] px-3.5 pb-4 pt-3 backdrop-blur-md">
          <div className="flex items-center gap-3.5">
            {/* Progress ring */}
            <div className="relative h-[92px] w-[92px] shrink-0">
              <svg viewBox="0 0 92 92" className="h-full w-full -rotate-90">
                <circle
                  cx="46"
                  cy="46"
                  r={RING_RADIUS}
                  fill="none"
                  stroke="rgba(255,255,255,0.07)"
                  strokeWidth="7"
                />
                <circle
                  data-ring-arc
                  cx="46"
                  cy="46"
                  r={RING_RADIUS}
                  fill="none"
                  stroke="url(#ringGold)"
                  strokeWidth="7"
                  strokeLinecap="round"
                  strokeDasharray={RING_CIRCUMFERENCE}
                  strokeDashoffset={ringDash}
                />
                <defs>
                  <linearGradient id="ringGold" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#E8C766" />
                    <stop offset="55%" stopColor="#D4AF37" />
                    <stop offset="100%" stopColor="#A8872A" />
                  </linearGradient>
                </defs>
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span
                  data-ring-value
                  className="text-[22px] font-bold leading-none text-white tabular-nums"
                >
                  {animated ? 0 : RING_TARGET}
                </span>
                <span className="mt-0.5 text-[7.5px] font-medium uppercase tracking-[0.12em] text-[var(--gold-light)]">
                  Fans
                </span>
                <span className="text-[7.5px] font-medium uppercase tracking-[0.12em] text-[var(--gold-light)]">
                  converted
                </span>
              </div>
            </div>

            {/* Widgety */}
            <div className="min-w-0 flex-1 space-y-2">
              <div
                data-widget
                style={hidden}
                className="widget-depth widget-depth-gold rounded-xl px-2.5 py-2"
              >
                <p className="flex items-center gap-1 text-[9px] font-medium text-white/55">
                  <Sparkles className="h-2.5 w-2.5 text-[var(--gold)]" />
                  New Fanvue subscriber
                </p>
                <p className="mt-0.5 text-[13px] font-bold text-[var(--gold-light)]">
                  💰 +$24.99
                </p>
              </div>
              <div
                data-widget
                style={hidden}
                className="widget-depth rounded-xl px-2.5 py-2"
              >
                <p className="flex items-center gap-1 text-[9px] font-medium text-white/55">
                  <Zap className="h-2.5 w-2.5 text-[var(--gold)]" />
                  Auto-reply sent
                </p>
                <p className="mt-0.5 text-[13px] font-bold text-white">2.3s ⚡</p>
              </div>
            </div>
          </div>
        </div>

        {/* Jemný lesk skla cez displej */}
        <div className="pointer-events-none absolute inset-0 rounded-[43px] bg-[linear-gradient(115deg,rgba(255,255,255,0.07)_0%,transparent_38%,transparent_62%,rgba(255,255,255,0.035)_100%)]" />
      </div>
    </div>
  );
}

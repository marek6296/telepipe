"use client";

import { useId, useState } from "react";
import Link from "next/link";
import NumberFlow, { type Format } from "@number-flow/react";
import { motion, useReducedMotion } from "framer-motion";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/*  Dáta                                                                       */
/* -------------------------------------------------------------------------- */

type Billing = "monthly" | "yearly";

type Plan = {
  id: string;
  name: string;
  tagline: string;
  monthly: number;
  yearly: number;
  cta: string;
  popular?: boolean;
  /** Prvá odrážka býva „Everything in X, plus" — vizuálne sa odlíši. */
  inherits?: string;
  features: string[];
};

/**
 * Balíky a ceny sú Marekove finálne (`docs/superpowers/plans/2026-08-17-marketing-pages.md`).
 * Odrážky opisujú výhradne to, čo produkt naozaj vie — persona/pamäť/rytmus
 * (worker: persona, memory, facts, humanize, den), hlasovky cez ElevenLabs
 * (eleven, voices, livevoice), Telegram userbot, Fanvue agent + vault s cenami,
 * kreditové účtovanie z `usage_events`, história chatov. Nič navyše.
 */
const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    tagline: "One model, the full brain. Pay only for the AI she uses.",
    monthly: 0,
    yearly: 0,
    cta: "Start free",
    features: [
      "1 model",
      "Telegram agent — she replies from her own account",
      "Persona: backstory, tone, slang and hard boundaries",
      "Long-term memory of every fan she talks to",
      "Human-like typing rhythm and daily activity waves",
      "Conversation history with funnel stages",
      "Usage-based AI credits — no minimum",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    tagline: "Voice, photos and the Fanvue side of the business.",
    monthly: 14.99,
    yearly: 143.9,
    cta: "Get Started",
    popular: true,
    inherits: "Free",
    features: [
      "Up to 5 models",
      "ElevenLabs voice notes with her own voice, tempo and ambience",
      "Photo library with per-photo captions, situations and limits",
      "Fanvue agent — replies to Fanvue DMs too",
      "Vault selling: priced media straight from her Fanvue folders",
      "Funnel rules — the link drops only when the chat is warm",
      "Daily usage and spend breakdown per model",
      "Priority email support",
    ],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    tagline: "A whole roster, set up with us and watched together.",
    monthly: 49.99,
    yearly: 479.9,
    cta: "Get Started",
    inherits: "Pro",
    features: [
      "Unlimited models",
      "Telegram and Fanvue on every model",
      "Guided onboarding — we connect and tune the first roster with you",
      "Persona and behaviour tuning together with our team",
      "Account-wide usage insight across every model",
      "Direct line to the people who build Telepipe",
    ],
  },
];

const usd: Format = {
  style: "currency",
  currency: "USD",
  // "$0" namiesto "$0.00" pri Free, ale "$14.99" ostáva presné.
  trailingZeroDisplay: "stripIfInteger",
};

/* -------------------------------------------------------------------------- */
/*  Prepínač mesačne / ročne                                                   */
/* -------------------------------------------------------------------------- */

function BillingSwitch({
  value,
  onChange,
}: {
  value: Billing;
  onChange: (next: Billing) => void;
}) {
  const layoutId = useId();
  const reduced = useReducedMotion();

  const options: { id: Billing; label: string }[] = [
    { id: "monthly", label: "Monthly" },
    { id: "yearly", label: "Yearly" },
  ];

  return (
    <div
      role="radiogroup"
      aria-label="Billing period"
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
                  reduced
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 420, damping: 36 }
                }
              />
            )}
            <span className="relative">{option.label}</span>
            {option.id === "yearly" && (
              <span
                className={cn(
                  "relative rounded-full px-1.5 py-0.5 text-[10px] font-semibold tracking-[0.02em] transition-colors",
                  active
                    ? "bg-black/10 text-[#0a0a0a]"
                    : "bg-white/[0.07] text-white/60",
                )}
              >
                Save 20%
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Cenník                                                                     */
/* -------------------------------------------------------------------------- */

export function PricingTable() {
  const [billing, setBilling] = useState<Billing>("monthly");
  const yearly = billing === "yearly";

  return (
    <div>
      <div className="flex justify-center">
        <BillingSwitch value={billing} onChange={setBilling} />
      </div>

      <div className="mt-12 grid gap-4 lg:grid-cols-3">
        {PLANS.map((plan) => {
          const price = yearly ? plan.yearly : plan.monthly;
          const perMonth = plan.yearly / 12;

          return (
            <article
              key={plan.id}
              className={cn(
                "relative flex flex-col overflow-hidden rounded-[20px] p-7",
                plan.popular ? "lp-plan-featured" : "lp-card",
              )}
            >
              {plan.popular && (
                <>
                  <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
                  <span className="lp-hairline absolute right-6 top-7 rounded-full bg-white/[0.06] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/70">
                    Most popular
                  </span>
                </>
              )}

              <div className="relative">
                <h2 className="text-[17px] font-semibold text-white">{plan.name}</h2>
                <p className="mt-2 min-h-[42px] max-w-[26ch] text-[13.5px] leading-relaxed text-white/40">
                  {plan.tagline}
                </p>

                <div className="mt-7 flex items-end gap-2">
                  <NumberFlow
                    value={price}
                    format={usd}
                    // `willChange` drží číslice na vlastnej vrstve počas rolovania
                    willChange
                    className="lp-tight text-[clamp(2.2rem,4vw,2.9rem)] font-semibold leading-none text-white tabular-nums"
                  />
                  <span className="pb-1 text-[13px] text-white/35">
                    {yearly ? "/year" : "/month"}
                  </span>
                </div>

                <p className="mt-2.5 h-4 text-[12px] text-white/30">
                  {plan.monthly === 0
                    ? "Free forever · usage billed in credits"
                    : yearly
                      ? `$${perMonth.toFixed(2)} per month, billed annually`
                      : "Billed monthly · cancel anytime"}
                </p>

                <Link
                  href="/register"
                  className={cn(
                    "lp-btn mt-7 h-11 w-full text-[14px]",
                    plan.popular ? "lp-btn-primary" : "lp-btn-ghost",
                  )}
                >
                  {plan.cta}
                </Link>
              </div>

              <div className="relative mt-8 border-t border-white/[0.07] pt-7">
                {plan.inherits && (
                  <p className="mb-4 text-[12.5px] font-medium text-white/55">
                    Everything in {plan.inherits}, plus
                  </p>
                )}
                <ul className="space-y-3">
                  {plan.features.map((feature) => (
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
        Plan price covers the platform. The AI itself is billed separately from
        your credit balance — every message, transcription and voice second is
        metered per model, to the cent.
      </p>
    </div>
  );
}

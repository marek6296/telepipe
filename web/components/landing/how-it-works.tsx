import Link from "next/link";
import { ArrowRight, Send, Sparkles, Wallet } from "lucide-react";

const STEPS = [
  {
    icon: Send,
    title: "Connect Telegram",
    body: "Paste your API credentials, confirm the SMS code, and link a control bot. Takes about three minutes — no server, no code, no Telethon.",
  },
  {
    icon: Sparkles,
    title: "Set up your model",
    body: "Name, age, city, backstory, tone, boundaries and the Fanvue link. Choose how spicy she gets and how often she sends voice notes.",
  },
  {
    icon: Wallet,
    title: "Watch credits convert",
    body: "The agent goes live within 30 seconds. Track chats, funnel stages and spend per model — and top up whenever the balance runs low.",
  },
];

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="relative scroll-mt-24 overflow-hidden px-6 py-28 sm:py-36"
    >
      <div className="pointer-events-none absolute left-1/2 top-0 h-[520px] w-[900px] -translate-x-1/2 gold-halo opacity-25" />

      <div className="relative mx-auto max-w-6xl">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.26em] text-[var(--gold)]">
            How it works
          </p>
          <h2 className="mt-4 text-[clamp(2rem,4.4vw,3.2rem)] font-semibold leading-[1.1] text-balance-tight text-white">
            Live in <span className="text-gradient-gold">three steps</span>
          </h2>
        </div>

        <ol className="mt-16 grid gap-5 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li
              key={step.title}
              className="widget-depth relative rounded-3xl p-7 pt-9"
            >
              {/* Spojnica medzi krokmi na desktope */}
              {index < STEPS.length - 1 && (
                <span
                  aria-hidden
                  className="absolute -right-3 top-1/2 hidden h-px w-6 bg-[linear-gradient(90deg,rgba(212,175,55,0.5),transparent)] md:block"
                />
              )}

              <span className="absolute -top-4 left-7 flex h-9 w-9 items-center justify-center rounded-full border border-[rgba(212,175,55,0.3)] bg-black text-[13px] font-bold text-[var(--gold)]">
                {index + 1}
              </span>

              <step.icon className="h-6 w-6 text-[var(--gold)]" />
              <h3 className="mt-5 text-lg font-semibold text-white">{step.title}</h3>
              <p className="mt-2.5 text-[14.5px] leading-relaxed text-white/50">
                {step.body}
              </p>
            </li>
          ))}
        </ol>

        {/* Pricing teaser — plná cenová stránka príde vo fáze 4 */}
        <div
          id="pricing"
          className="premium-depth-card relative mt-24 scroll-mt-24 overflow-hidden rounded-[32px] px-8 py-14 text-center sm:px-14"
        >
          <div className="pointer-events-none absolute inset-0 bg-grid-fine" />
          <div className="relative">
            <p className="text-[11px] font-semibold uppercase tracking-[0.26em] text-[var(--gold)]">
              Pricing
            </p>
            <h2 className="mx-auto mt-4 max-w-2xl text-[clamp(1.8rem,3.6vw,2.6rem)] font-semibold leading-tight text-balance-tight text-white">
              Pay only for what your models actually say.
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-white/50">
              Usage-based credits, billed per message, transcription and voice
              second. Detailed plans land soon — start now and we will top up your
              test balance.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link href="/register" className="btn-modern-light h-13 px-8 text-[15px]">
                Get Started
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/login" className="btn-modern-dark h-13 px-8 text-[15px]">
                Sign In
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

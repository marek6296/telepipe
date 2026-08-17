import Link from "next/link";
import { ArrowRight, Send, SlidersHorizontal, Wallet } from "lucide-react";

const STEPS = [
  {
    icon: Send,
    title: "Connect Telegram",
    body: "Paste your API credentials, confirm the SMS code, and link a control bot. Takes about three minutes — no server, no code, no Telethon.",
  },
  {
    icon: SlidersHorizontal,
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
      <div className="lp-halo pointer-events-none absolute left-1/2 top-0 h-[520px] w-[900px] -translate-x-1/2 opacity-30" />

      <div className="relative mx-auto max-w-6xl">
        <div className="mx-auto max-w-2xl text-center">
          <p className="lp-eyebrow">How it works</p>
          <h2 className="mt-4 text-[clamp(2rem,4.4vw,3.2rem)] font-semibold leading-[1.1] lp-tight text-white">
            Live in <span className="lp-text-dim">three steps</span>
          </h2>
        </div>

        <ol className="mt-16 grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="lp-card relative p-7 pt-9">
              {/* Spojnica medzi krokmi na desktope */}
              {index < STEPS.length - 1 && (
                <span
                  aria-hidden
                  className="absolute -right-2.5 top-1/2 hidden h-px w-5 bg-[linear-gradient(90deg,rgba(255,255,255,0.22),transparent)] md:block"
                />
              )}

              <span className="lp-hairline absolute -top-3.5 left-7 flex h-8 w-8 items-center justify-center rounded-lg bg-[#0a0a0a] font-mono text-[12px] font-semibold text-white/70">
                {index + 1}
              </span>

              <step.icon className="h-5 w-5 text-white/60" strokeWidth={1.5} />
              <h3 className="mt-5 text-[17px] font-semibold text-white">{step.title}</h3>
              <p className="mt-2.5 text-[14.5px] leading-relaxed text-white/45">
                {step.body}
              </p>
            </li>
          ))}
        </ol>

        {/* Pricing teaser — plná cenová stránka príde vo fáze 4 */}
        <div
          id="pricing"
          className="lp-depth-card relative mt-24 scroll-mt-24 overflow-hidden rounded-[28px] px-8 py-14 text-center sm:px-14"
        >
          <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
          <div className="relative">
            <p className="lp-eyebrow">Pricing</p>
            <h2 className="mx-auto mt-4 max-w-2xl text-[clamp(1.8rem,3.6vw,2.6rem)] font-semibold leading-tight lp-tight text-white">
              Pay only for what your models actually say.
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-white/45">
              Usage-based credits, billed per message, transcription and voice
              second. Detailed plans land soon — start now and we will top up your
              test balance.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href="/register"
                className="lp-btn lp-btn-primary h-12 px-7 text-[14.5px]"
              >
                Get Started
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/login" className="lp-btn lp-btn-ghost h-12 px-7 text-[14.5px]">
                Sign In
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

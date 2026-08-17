import type { Metadata } from "next";

import { CtaBand, PageHeader } from "@/components/marketing/page-shell";
import { PricingTable } from "@/components/marketing/pricing-table";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Telepipe plans: Free, Pro at $14.99/mo and Enterprise at $49.99/mo — 20% off yearly. The platform is a flat fee, the AI itself is billed from usage-based credits.",
  openGraph: {
    title: "Pricing · Telepipe",
    description:
      "Free, Pro and Enterprise plans for AI chat agents on Telegram and Fanvue. Save 20% yearly.",
  },
};

const FAQ = [
  {
    q: "What exactly do credits pay for?",
    a: "Every AI call your model makes — replies, chat summaries, image understanding, voice transcription and generated voice notes. Each one is metered and shown per model, per day, to the cent.",
  },
  {
    q: "What happens when the balance hits zero?",
    a: "The model pauses instead of running up a bill. She stops replying, you get a message from her control bot, and everything resumes the moment you top the balance back up.",
  },
  {
    q: "Do I need my own Telegram infrastructure?",
    a: "No. You sign in with your phone number right on the page, create a control bot, and Telepipe keeps the session encrypted. No server, no code.",
  },
  {
    q: "Can I switch plans later?",
    a: "Yes — plans only gate how many models you run and which channels they use. Personas, memory and history stay exactly where they are.",
  },
];

export default function PricingPage() {
  return (
    <>
      <section className="relative overflow-hidden px-6 pb-20 pt-36 sm:pt-44">
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          aria-hidden
          className="lp-halo pointer-events-none absolute left-1/2 top-10 h-[560px] w-[860px] -translate-x-1/2 opacity-30"
        />

        <div className="relative mx-auto max-w-6xl">
          <PageHeader
            eyebrow="Pricing"
            title="One flat platform fee."
            dim="The AI is billed by the message."
            lead="No seats, no per-chat pricing, no minimum. Pick how many models you run — the tokens, transcriptions and voice seconds they actually use come out of your credit balance."
          />

          <div className="mt-16">
            <PricingTable />
          </div>
        </div>
      </section>

      <section className="relative px-6 pb-24">
        <div className="mx-auto grid max-w-4xl gap-4 sm:grid-cols-2">
          {FAQ.map((item) => (
            <div key={item.q} className="lp-card p-6">
              <h3 className="text-[14.5px] font-semibold text-white">{item.q}</h3>
              <p className="mt-2.5 text-[13.5px] leading-relaxed text-white/45">
                {item.a}
              </p>
            </div>
          ))}
        </div>
      </section>

      <CtaBand
        title="Start on Free. Move up when she pays for herself."
        body="Connect one model in a few minutes and watch what she does with your DMs before you spend anything on the platform."
        note="No card required · Usage-based credits · Cancel anytime"
      />
    </>
  );
}

import type { Metadata } from "next";

import { CtaBand, PageHeader } from "@/components/marketing/page-shell";
import { PricingTable } from "@/components/marketing/pricing-table";
import { COINS_PER_REPLY, COINS_PER_USD } from "@/lib/coins";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Telegram Chatbot Pricing",
  description:
    "No subscription. Buy Pipe Coins — $50 for 50,000, $100 for 110,000, $250 for 300,000 — and spend them as your models work. Every reply, transcription and voice second metered to the coin.",
  path: "/pricing",
});

/**
 * FAQ hovorí o coinoch, nie o balíkoch predplatného — a čísla v ňom sú odmerané,
 * nie vymyslené: `COINS_PER_REPLY` je celý týždenný náklad živej modelky delený
 * počtom SKUTOČNE odoslaných odpovedí, zaokrúhlený nahor (viď `lib/coins.ts`).
 * Nikdy to nepočítaj z riadkov `kind='chat'` — tam sedí aj interná práca.
 */
const FAQ = [
  {
    q: "What is a Pipe Coin?",
    a: `It is the unit your balance is counted in. ${COINS_PER_USD.toLocaleString(
      "en-US",
    )} Pipe Coins is one dollar of balance, so a $50 pack lands as 50,000 coins. Everything your models do is priced in coins, so you always see the cost in the same unit you bought.`,
  },
  {
    q: "So what does one reply actually cost?",
    a: `About ${COINS_PER_REPLY} Pipe Coins, all in. That is measured from a real week of live traffic: every coin the account spent — the reply itself, the memory work behind it, transcribing the voice notes he sent her — divided by the replies she actually sent. A quick back-and-forth costs less; a long conversation where she is pulling in months of memory about that fan costs more.`,
  },
  {
    q: "Is there a subscription?",
    a: "No. There are no plans, no seats and nothing renews. You buy Pipe Coins when you want them and spend them as your models work. Run one model or ten — the coins are the only bill.",
  },
  {
    q: "Do Pipe Coins expire?",
    a: "Never. They sit on your balance until your models spend them. Take a month off and they will still be there when you come back.",
  },
  {
    q: "What happens when the balance hits zero?",
    a: "Your models pause instead of running up a bill. They stop replying, you get a message from the control bot, and everything resumes the moment you top up — personas, memory and conversation history stay exactly where they were.",
  },
  {
    q: "Why is the bigger pack cheaper per coin?",
    a: "Because a bigger top-up costs us less to handle. $50 is 1,000 coins per dollar, $100 is 1,100, $250 is 1,200 — same coins, same models, just a better rate the more you buy at once.",
  },
  {
    q: "Do I need my own Telegram infrastructure?",
    a: "No. You sign in with your phone number right on the page, create a control bot, and Telepipe keeps the session encrypted. No server, no code.",
  },
  {
    q: "How do I pay?",
    a: "Crypto checkout is being wired up right now. Until it goes live, pick a pack and email us — we credit your balance by hand, usually the same day.",
  },
];

export default function PricingPage() {
  return (
    <>
      <section className="relative overflow-hidden px-6 pb-20 pt-[92px]">
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          aria-hidden
          className="lp-halo pointer-events-none absolute left-1/2 top-10 h-[560px] w-[860px] -translate-x-1/2 opacity-30"
        />

        <div className="relative mx-auto max-w-6xl">
          <PageHeader
            eyebrow="Pricing"
            title="No subscription."
            dim="You buy Pipe Coins and spend them as she works."
            lead="No plans, no seats, no renewals, no minimum. Top up your balance once — every reply, transcription and voice second comes off it as it happens, metered per model to the coin. The bigger the pack, the better the rate."
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
        title="Start free. Buy coins when she has earned them."
        body="Connect one model in a few minutes and watch what she does with your DMs. You only ever pay for the work she actually does."
        note="No card required · No subscription · Pipe Coins never expire"
      />
    </>
  );
}

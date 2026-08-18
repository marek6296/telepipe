import type { Metadata } from "next";

import { FeatureGrid } from "@/components/marketing/feature-grid";
import { CtaBand, PageHeader } from "@/components/marketing/page-shell";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Chatbot Features for Telegram & Fanvue",
  description:
    "What Telepipe actually does: an AI persona with long-term memory, human-like typing rhythm, ElevenLabs voice notes, a Telegram agent, a Fanvue agent with vault selling, and Pipe Coins you can see spent to the coin.",
  path: "/features",
});

export default function FeaturesPage() {
  return (
    <>
      <section className="relative overflow-hidden px-6 pb-16 pt-[92px]">
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          aria-hidden
          className="lp-halo pointer-events-none absolute left-1/2 top-4 h-[520px] w-[900px] -translate-x-1/2 opacity-30"
        />

        <div className="relative mx-auto max-w-6xl">
          <PageHeader
            eyebrow="Features"
            title="Everything a chatter does."
            dim="Without the payroll."
            lead="Telepipe replaces the night shift, the weekend shift and the “sorry, I was asleep” shift — one agent per model that keeps her voice, her memory and her boundaries in every conversation."
          />
        </div>
      </section>

      <section className="relative px-6 pb-24">
        <FeatureGrid />
      </section>

      <CtaBand
        title="See her handle your inbox for a day."
        body="Connect one model and see her work — persona, memory and the Telegram agent are all included. There is no subscription: you buy Pipe Coins and spend them as she replies."
        note="No card required · No subscription · Pipe Coins never expire"
      />
    </>
  );
}

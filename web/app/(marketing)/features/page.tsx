import type { Metadata } from "next";

import { FeatureGrid } from "@/components/marketing/feature-grid";
import { CtaBand, PageHeader } from "@/components/marketing/page-shell";

export const metadata: Metadata = {
  title: "Features",
  description:
    "What Telepipe actually does: an AI persona with long-term memory, human-like typing rhythm, ElevenLabs voice notes, a Telegram agent, a Fanvue agent with vault selling, and usage-based credits you can see to the cent.",
  openGraph: {
    title: "Features · Telepipe",
    description:
      "Persona with memory, human rhythm, voice notes, Telegram and Fanvue agents, usage-based credits.",
  },
};

export default function FeaturesPage() {
  return (
    <>
      <section className="relative overflow-hidden px-6 pb-16 pt-36 sm:pt-44">
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
        body="Connect one model on the Free plan — persona, memory and the Telegram agent are all included before you pay a cent for the platform."
        note="No card required · Usage-based credits · Cancel anytime"
      />
    </>
  );
}

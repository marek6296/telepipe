import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { CtaBand, PageHeader } from "@/components/marketing/page-shell";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "Telegram AI Automation Guides",
  description:
    "Practical Telepipe guides to Telegram AI chat automation, virtual-number verification and the operational differences between AI and human chatters.",
  path: "/guides",
});

const GUIDES = [
  {
    href: "/guides/automate-telegram-dms-with-ai",
    category: "Automation",
    title: "How to automate Telegram DMs with AI",
    body: "A practical architecture for persona, memory, timing, safety controls and human oversight — beyond simply connecting a language model to Telegram.",
    read: "8 min read",
  },
  {
    href: "/guides/telegram-virtual-number-verification",
    category: "Telegram setup",
    title: "Telegram verification with a virtual number",
    body: "What temporary OTP numbers do, how the verification window works and which account-security steps to take after the code arrives.",
    read: "6 min read",
  },
  {
    href: "/guides/telegram-to-onlyfans-funnel",
    category: "Funnel",
    title: "The Telegram to OnlyFans funnel, measured",
    body: "What happens between the first DM and the first payment — when the link goes out, and the three numbers that say which half of the funnel is broken.",
    read: "9 min read",
  },
  {
    href: "/guides/onlyfans-traffic-sources",
    category: "Traffic",
    title: "Creator traffic sources, and which you own",
    body: "Reddit, Instagram, TikTok, X, Telegram and paid — what each costs in hours, which can be taken away overnight, and where the middle leaks.",
    read: "8 min read",
  },
  {
    href: "/guides/how-to-get-fanvue-subscribers",
    category: "Fanvue",
    title: "How to get Fanvue subscribers, and keep them",
    body: "Why nobody browses Fanvue, when the link should go out, and why the first message after someone subscribes decides whether they spend again.",
    read: "7 min read",
  },
  {
    href: "/guides/ai-chatter-vs-human-chatter",
    category: "Operations",
    title: "AI chatter vs human chatter",
    body: "A grounded comparison of coverage, consistency, cost, judgment and the workflows where a human operator still matters.",
    read: "7 min read",
  },
] as const;

export default function GuidesPage() {
  return (
    <>
      <section className="relative overflow-hidden px-6 pb-16 pt-[112px] sm:pb-20 sm:pt-[132px]">
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          aria-hidden
          className="lp-halo pointer-events-none absolute left-1/2 top-0 h-[520px] w-[860px] -translate-x-1/2 opacity-30"
        />
        <div className="relative mx-auto max-w-6xl">
          <PageHeader
            eyebrow="Guides"
            title="Telegram AI automation,"
            dim="explained without the shortcuts."
            lead="Practical guides based on the product we operate: connected Telegram accounts, persistent personas, conversation memory, voice and one-time OTP setup."
          />

          <div className="mt-14 grid gap-5 lg:grid-cols-3">
            {GUIDES.map((guide, index) => (
              <Link
                key={guide.href}
                href={guide.href}
                className="lp-card lp-card-hover group flex min-h-[320px] flex-col p-7"
              >
                <div className="flex items-center justify-between text-[10.5px] uppercase tracking-[0.18em] text-white/30">
                  <span>{guide.category}</span>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                </div>
                <h2 className="lp-tight mt-10 text-[22px] font-semibold leading-tight text-white">
                  {guide.title}
                </h2>
                <p className="mt-4 text-[13.5px] leading-6 text-white/45">{guide.body}</p>
                <span className="mt-auto flex items-center justify-between pt-10 text-[12px] text-white/35">
                  {guide.read}
                  <ArrowRight
                    className="h-4 w-4 transition-transform group-hover:translate-x-1"
                    strokeWidth={1.6}
                  />
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <CtaBand
        title="Put the workflow into practice."
        body="Create a model, configure the identity and connect Telegram from one guided workspace."
        note="No card required · Usage-based Pipe Coins · Pause any time"
      />
    </>
  );
}

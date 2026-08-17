import type { Metadata } from "next";

import { CtaBand, PageHeader } from "@/components/marketing/page-shell";
import { StepsInteractor, type Step } from "@/components/marketing/steps-interactor";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "Three steps to a model that never sleeps: connect Telegram with a phone code, set up her persona, voice and photos, and let her reply 24/7 — dropping the link only when the chat is warm.",
  openGraph: {
    title: "How it works · Telepipe",
    description:
      "Connect Telegram, set up your model, and let her reply around the clock.",
  },
};

const STEPS: Step[] = [
  {
    title: "Connect Telegram",
    body: "Create a control bot in BotFather, then sign in with her phone number right on the page — the code arrives in Telegram, you type it in, and the session is encrypted before it ever touches the database. No server, no code, no Telethon.",
    image: "/how-it-works/01-connect.svg",
    alt: "Signing in to Telegram with a phone code",
  },
  {
    title: "Set up your model",
    body: "Her backstory, tone, slang and hard boundaries. How spicy she gets, how often she sends a voice note, which hours she is awake. Add her photos and her Fanvue link, and it is live — no restart, she reads the changes on her next reply.",
    image: "/how-it-works/02-model.svg",
    alt: "The model setup screen with persona fields, sliders and photos",
  },
  {
    title: "She replies and converts",
    body: "From that moment she answers every DM around the clock, in her own rhythm, remembering what each fan told her. Voice notes when it fits, the link when the chat is warm — and every message metered so you always know what it cost.",
    image: "/how-it-works/03-convert.svg",
    alt: "A live chat with a voice note and a daily conversions chart",
  },
];

export default function HowItWorksPage() {
  return (
    <>
      <section className="relative overflow-hidden px-6 pb-16 pt-36 sm:pt-44">
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          aria-hidden
          className="lp-halo pointer-events-none absolute left-1/2 top-4 h-[500px] w-[880px] -translate-x-1/2 opacity-30"
        />

        <div className="relative mx-auto max-w-6xl">
          <PageHeader
            eyebrow="How it works"
            title="Live in three steps."
            dim="About an evening of work."
            lead="No infrastructure, no prompt engineering, no chatters to schedule. Connect the account, describe who she is, and let her run."
          />
        </div>
      </section>

      <section className="relative px-6 pb-24">
        <div className="mx-auto max-w-6xl">
          <StepsInteractor steps={STEPS} />
        </div>
      </section>

      <CtaBand
        title="Three steps away from a model that never sleeps."
        body="Start on Free with a single model — Telegram, persona and memory are all in there before you pay anything for the platform."
        note="No card required · Usage-based credits · Cancel anytime"
      />
    </>
  );
}

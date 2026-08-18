import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "Telegram Automation for Creator DMs",
  description:
    "Automate creator Telegram DMs with a persistent AI persona, conversation memory, human reply timing, voice notes and operator-owned controls.",
  path: "/telegram-automation",
});

const FAQ = [
  {
    q: "What can Telepipe automate on Telegram?",
    a: "Telepipe can handle configured creator conversations with persona-aware text replies, fan-level memory, approved photos, voice notes and controlled links. Operators keep access to conversations, settings and pause controls.",
  },
  {
    q: "Is Telegram automation the same as a public Telegram bot?",
    a: "No. Public bots created with BotFather are separate bot identities. Telepipe is designed around a connected creator account and its configured model workspace, so the operational and security requirements are different.",
  },
  {
    q: "Can replies be delayed instead of sent instantly?",
    a: "Yes. Reply pacing and daily-life settings help avoid identical machine-speed responses at every hour while still providing dependable coverage.",
  },
  {
    q: "Can an agency automate more than one creator?",
    a: "Yes. Each model has a separate persona, memory, Telegram connection and asset library inside the same agency workspace.",
  },
  {
    q: "Can I stop the automation immediately?",
    a: "Yes. A model can be paused from the dashboard without deleting its saved identity, memory or configuration.",
  },
];

export default function TelegramAutomationPage() {
  return (
    <SeoPage
      path="/telegram-automation"
      eyebrow="Telegram automation"
      title="Telegram automation for creator DMs."
      dim="Persistent context, not canned replies."
      lead="Telepipe combines a connected Telegram identity with persona rules, fan memory, believable timing and operator controls so routine conversations keep moving without becoming generic bot scripts."
      highlights={[
        {
          title: "One identity per model",
          body: "Backstory, tone, vocabulary and boundaries stay attached to the correct creator instead of leaking across an agency roster.",
        },
        {
          title: "Context in every conversation",
          body: "Useful fan facts and earlier topics return with the correct chat, reducing repetitive introductions and broken promises.",
        },
        {
          title: "Automation with an off switch",
          body: "Operators can inspect conversations, protect contacts, control usage and pause a model without rebuilding its settings.",
        },
      ]}
      sections={[
        {
          title: "What useful Telegram automation includes",
          paragraphs: [
            "Sending a fixed welcome message is automation, but it is not enough for an ongoing creator conversation. Reliable Telegram automation needs to know which identity it represents, what happened earlier in the chat and which actions are allowed next.",
            "Telepipe stores those layers in a model workspace: identity and behavior, conversation memory, daily rhythm, voice, approved media and conversion rules. The agent answers against that configuration rather than inventing a new personality in every thread.",
          ],
          points: [
            "Structured creator persona",
            "Fan-level conversation memory",
            "Schedule-aware reply pacing",
            "Approved voice, photos and links",
          ],
        },
        {
          title: "Connected account automation versus a Telegram bot",
          paragraphs: [
            "A public Telegram bot is a distinct bot account created through BotFather. It is useful for commands, support flows and group utilities, but it does not automatically become the creator identity fans already message.",
            "Telepipe's workflow is built around connecting the authorized creator account from the dashboard. The session is handled server-side, and saved contacts can be protected so personal conversations do not unexpectedly enter the automated workflow.",
          ],
        },
        {
          title: "Human-like timing without pretending nobody is in control",
          paragraphs: [
            "Constant replies in a few milliseconds make an automated account obvious and ignore the model's configured daily life. Telepipe uses variable pacing and activity context so responses do not all share the same mechanical rhythm.",
            "Timing is only one part of responsible operation. The creator or agency remains responsible for the represented identity, approved content, platform compliance and the situations that should be reviewed by a human.",
          ],
        },
        {
          title: "Telegram automation for agencies",
          paragraphs: [
            "An agency needs separation as much as speed. Every model must retain her own Telegram connection, persona, fan memories, photos, voice and usage trail when an operator moves between workspaces.",
            "Telepipe keeps those model records separate while presenting them through one dashboard. That makes it possible to expand a roster without copying one giant prompt or sharing context between unrelated creators.",
          ],
        },
        {
          title: "Measure the work and keep limits visible",
          paragraphs: [
            "Reply volume alone is not a useful definition of success. Track active conversations, usage spend and conversion events where they can be measured accurately, then review the conversations that need better rules or human judgment.",
            "Telepipe meters AI, memory, transcription and voice work through Pipe Coins. The visible balance and per-model pause controls prevent an automation workflow from becoming an open-ended process with no operational limit.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/telegram-ai-chatbot",
          label: "Telegram AI chatbot",
          description: "Explore the persona, memory, voice and conversion layers in the product.",
        },
        {
          href: "/guides/automate-telegram-dms-with-ai",
          label: "Automation guide",
          description: "A six-layer checklist for building controlled Telegram DM automation.",
        },
        {
          href: "/ai-chatter",
          label: "AI chatter",
          description: "See how routine chat coverage works for creators and agencies.",
        },
      ]}
      ctaTitle="Turn Telegram conversations into a controlled workflow."
      ctaBody="Connect one authorized account, define the creator persona and review how the automation behaves before expanding the roster."
      ctaNote="One model first · Human-owned rules · Pause any time"
    />
  );
}

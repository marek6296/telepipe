import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Chatbot for Creators Who Sell Through DMs",
  description:
    "Keep creator DMs moving with a persona-driven AI chatbot for Telegram and Fanvue, including memory, voice notes, photos and controlled conversion links.",
  path: "/ai-chatbot-for-creators",
});

const FAQ = [
  {
    q: "Do I need to write prompts for every reply?",
    a: "No. You configure the creator's identity, behavior, boundaries and daily life in the dashboard. The agent uses that profile when handling conversations.",
  },
  {
    q: "Can I still open and review conversations?",
    a: "Yes. Telegram and Fanvue conversation views stay available in the model workspace so you can inspect the history and the fan memory attached to it.",
  },
  {
    q: "Can it use my photos and voice?",
    a: "You can upload approved photo sets and configure a cloned voice. The model's rules determine when those assets can be used.",
  },
  {
    q: "Will it message my personal Telegram contacts?",
    a: "Contact protection can keep saved contacts outside automation, with explicit exceptions controlled from the model's Telegram settings.",
  },
  {
    q: "Is there a monthly subscription?",
    a: "Telepipe currently uses prepaid Pipe Coins rather than recurring per-seat plans. The visible balance is spent as the model works.",
  },
];

export default function AiChatbotForCreatorsPage() {
  return (
    <SeoPage
      path="/ai-chatbot-for-creators"
      eyebrow="For creators"
      title="An AI chatbot for creators."
      dim="Built around your identity."
      lead="Stay responsive in Telegram and Fanvue without turning every hour into inbox time. Telepipe keeps your configured persona and rules attached to every conversation."
      highlights={[
        {
          title: "Keep the character consistent",
          body: "Your backstory, texting style, limits and approved selling flow guide the model in every thread.",
        },
        {
          title: "Remember returning fans",
          body: "Conversation memory gives the agent context from earlier chats instead of treating every DM like a first contact.",
        },
        {
          title: "Stay in control",
          body: "Pause the model, update settings, protect contacts and review usage from one workspace.",
        },
      ]}
      sections={[
        {
          title: "The inbox problem for growing creators",
          paragraphs: [
            "DMs often arrive outside working hours and returning fans expect the conversation to remember them. Generic canned replies may be fast, but they lose the creator's voice and ignore the context that made the fan write again.",
            "Telepipe turns the identity behind the account into structured settings: who she is, how she writes, what she will not say, when she is awake and what links or assets she may use.",
          ],
        },
        {
          title: "A creator chatbot that uses your approved material",
          paragraphs: [
            "Photos, Fanvue links and voice settings are managed inside the model workspace. The agent can draw on those approved resources without inventing a new offer or personality for each conversation.",
            "Voice notes use the configured voice and schedule context. Photo sets can be organized around moments so the conversation does not jump randomly between unrelated material.",
          ],
          points: [
            "Approved photo library",
            "Configured voice and ambience",
            "Fanvue link settings",
            "Hard conversational boundaries",
          ],
        },
        {
          title: "Automation that can be changed while it runs",
          paragraphs: [
            "You can adjust persona, behavior and daily-life settings from the dashboard. The model reads updated configuration on future work instead of requiring a new server or automation rebuild.",
            "When you want to take a break, pause the model. The profile, memory and conversation history remain available rather than being discarded.",
          ],
        },
        {
          title: "Pay for usage instead of an empty seat",
          paragraphs: [
            "Pipe Coins keep replies, transcription, memory work and generated voice usage under one visible balance. A creator with a quiet inbox does not need to justify the same recurring seat cost as a busy agency model.",
            "The pricing page shows the available top-up packs and an estimate based on measured live usage. Actual conversations vary with message length, context and media work.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/alternatives/supercreator-alternative",
          label: "Supercreator alternative",
          description: "Where the conversation happens, and what it costs.",
        },
        {
          href: "/telegram-ai-chatbot",
          label: "Telegram AI chatbot",
          description: "See the product capabilities behind the connected inbox.",
        },
        {
          href: "/features",
          label: "All features",
          description: "Persona, voice, Telegram, Fanvue and transparent usage.",
        },
        {
          href: "/pricing",
          label: "Pipe Coin pricing",
          description: "Review usage-based top-ups without recurring seats.",
        },
      ]}
      ctaTitle="Spend less time watching the inbox."
      ctaBody="Build the model profile once, connect your account and keep control from the Telepipe workspace."
      ctaNote="Start with one model · No card required · Pause any time"
    />
  );
}

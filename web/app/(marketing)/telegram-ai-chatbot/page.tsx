import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Telegram Chatbot for Creator Conversations",
  description:
    "Use a persistent AI Telegram chatbot that remembers fans, follows a defined persona, sends voice notes and knows when to share the right creator link.",
  path: "/telegram-ai-chatbot",
});

const FAQ = [
  {
    q: "Is Telepipe a Telegram bot or a connected account?",
    a: "Telepipe connects the creator's Telegram account and runs the configured agent around it. The dashboard guides the sign-in and keeps the session encrypted.",
  },
  {
    q: "Can the AI keep one consistent personality?",
    a: "Yes. You define identity, tone, vocabulary, boundaries and daily life once. The agent uses those settings together with conversation memory on future replies.",
  },
  {
    q: "Does it support voice messages?",
    a: "Yes. A model can use a configured cloned voice, with controls for pace, voice-note frequency and the background ambience associated with her schedule.",
  },
  {
    q: "Can I pause the Telegram AI chatbot?",
    a: "Yes. Models can be paused from the dashboard without deleting their persona, memory or conversation history.",
  },
  {
    q: "How is usage billed?",
    a: "Telepipe uses Pipe Coins. Replies, memory work, transcription and voice generation draw from the visible balance instead of a recurring seat subscription.",
  },
];

export default function TelegramAiChatbotPage() {
  return (
    <SeoPage
      path="/telegram-ai-chatbot"
      eyebrow="Telegram AI chatbot"
      title="An AI Telegram chatbot."
      dim="With a real persona behind every reply."
      lead="Telepipe handles Telegram DMs around the clock while keeping the creator's identity, tone, boundaries and conversation history consistent."
      highlights={[
        {
          title: "Persistent persona",
          body: "Identity, tone, slang and hard boundaries live in one model profile instead of being improvised in every chat.",
        },
        {
          title: "Conversation memory",
          body: "Names, facts, earlier topics and promises stay connected to the fan who shared them.",
        },
        {
          title: "Voice and conversion flow",
          body: "Voice notes and creator links arrive according to the rules you set, not as random scripted blasts.",
        },
      ]}
      sections={[
        {
          title: "What an AI Telegram chatbot should actually do",
          paragraphs: [
            "A useful Telegram AI chatbot is more than a generic language model connected to an inbox. It needs a stable identity, access to the right conversation context and clear rules for what it may say or send.",
            "Telepipe gives every model her own persona, memory, daily rhythm, voice and boundaries. Incoming Telegram conversations are handled against that configuration so the same person shows up in every thread.",
          ],
        },
        {
          title: "Human timing without a night shift",
          paragraphs: [
            "Replies are paced instead of appearing with machine-like instant timing. Activity windows and daily-life settings influence when the agent is awake, how quickly she answers and what she can naturally say she is doing.",
            "The goal is operational consistency: fans get an answer while the creator or agency keeps control of the identity and rules behind it.",
          ],
          points: [
            "Configurable reply rhythm",
            "Schedule-aware conversation context",
            "Pause controls per model",
            "Contact and exception controls",
          ],
        },
        {
          title: "From conversation to the right next step",
          paragraphs: [
            "The agent can use the creator's approved links and selling flow when a conversation is ready for them. It does not need to drop the same link into every first message.",
            "Fanvue settings, Telegram photos and voice messages sit inside the same workspace, so the operator can see and adjust the material the model is allowed to use.",
          ],
        },
        {
          title: "One dashboard for the work behind the chat",
          paragraphs: [
            "The Telepipe dashboard exposes model status, conversations, usage and the settings that influence replies. Agencies can move between models without rebuilding separate automation stacks for each identity.",
            "Usage is metered in Pipe Coins. When the balance reaches zero, models pause instead of creating an open-ended bill, and the saved configuration remains in place for the next top-up.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/ai-chatbot-for-creators",
          label: "For creators",
          description: "How one creator can keep DMs moving without living in the inbox.",
        },
        {
          href: "/ai-chatbot-for-model-agencies",
          label: "For model agencies",
          description: "One workspace for multiple model personas and conversations.",
        },
        {
          href: "/how-it-works",
          label: "How it works",
          description: "Connect Telegram, configure the model and switch her on.",
        },
      ]}
      ctaTitle="Give every Telegram conversation a consistent answer."
      ctaBody="Create one model, define who she is and connect the Telegram account from the guided dashboard."
      ctaNote="No card required · Usage-based Pipe Coins · Pause any time"
    />
  );
}

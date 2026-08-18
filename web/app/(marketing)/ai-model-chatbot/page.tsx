import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Model Chatbot for Virtual Creators",
  description:
    "Run an AI model chatbot for virtual creators with a persistent character, fan memory, Telegram and Fanvue conversations, voice notes and controlled media.",
  path: "/ai-model-chatbot",
});

const FAQ = [
  {
    q: "What is an AI model chatbot?",
    a: "It is a conversation agent that represents a virtual creator or model using a documented identity, communication style, memory and approved content rules.",
  },
  {
    q: "Is this a consumer AI girlfriend app?",
    a: "No. Telepipe is an operator platform for creators and agencies managing authorized Telegram and Fanvue conversations. It is not a public directory of companion characters.",
  },
  {
    q: "Can every AI model have a different personality?",
    a: "Yes. Each model has separate identity, behavior, daily-life, voice, media and conversation-memory settings.",
  },
  {
    q: "Can a virtual creator send voice notes?",
    a: "A model can use a configured cloned voice with controls for voice-note frequency, pace and schedule-related ambience.",
  },
  {
    q: "Can agencies manage multiple AI models?",
    a: "Yes. The dashboard keeps model configurations and conversation context separated while allowing operators to move through one roster.",
  },
];

export default function AiModelChatbotPage() {
  return (
    <SeoPage
      path="/ai-model-chatbot"
      eyebrow="AI model chatbot"
      title="A chatbot built around one AI model."
      dim="Not a generic character generator."
      lead="Telepipe helps virtual creators and model agencies operate consistent Telegram and Fanvue conversations using a structured identity, fan memory, approved media and human-owned controls."
      highlights={[
        {
          title: "Character continuity",
          body: "Backstory, tone, slang, boundaries and daily life remain attached to the model across every fan conversation.",
        },
        {
          title: "Multimodal conversation tools",
          body: "Text, approved photos, conversion links and a configured voice sit inside the same model workspace.",
        },
        {
          title: "Agency separation",
          body: "Every AI model keeps her own settings and memories when an operator moves through a larger roster.",
        },
      ]}
      sections={[
        {
          title: "What makes an AI model chatbot believable",
          paragraphs: [
            "A consistent virtual creator needs more than a name and a profile picture. Fans notice when facts change, vocabulary jumps between styles or a conversation forgets what was promised earlier.",
            "Telepipe separates stable identity from behavior, daily life and fan memory. The chatbot combines those records when replying so the model can remain recognizable without forcing every detail into one oversized prompt.",
          ],
          points: [
            "Stable identity and backstory",
            "Defined texting style and vocabulary",
            "Daily rhythm and reply pacing",
            "Hard boundaries and operator exceptions",
          ],
        },
        {
          title: "AI model chatbot versus an AI girl chatbot",
          paragraphs: [
            "People sometimes use the phrase AI girl chatbot for consumer companion apps where visitors choose a public character and start a new chat. Telepipe serves a different intent: it is software for the creator or agency operating an authorized model identity and its existing fan conversations.",
            "The dashboard focuses on model configuration, connected channels, fan context, media controls, usage and conversion workflow. It does not publish a consumer character marketplace or invite anonymous users to create unowned identities.",
          ],
        },
        {
          title: "Connect the character to Telegram and Fanvue",
          paragraphs: [
            "Telegram provides direct creator conversations, while Fanvue provides the subscription-side inbox and approved creator link. Telepipe keeps both channel settings inside the same model workspace instead of treating the character as unrelated bots on each platform.",
            "Channel conversations still remain distinct. The operator can inspect chats and assets while the model profile provides the stable identity shared across the operation.",
          ],
        },
        {
          title: "Use approved voice and media",
          paragraphs: [
            "A virtual creator often communicates through more than text. Telepipe supports configured voice messages and approved photo sets so the chatbot does not need unrestricted access to invent or upload media.",
            "Operators remain responsible for consent, rights and platform rules around every asset and cloned voice. The model configuration controls availability; it does not replace that responsibility.",
          ],
        },
        {
          title: "Scale an AI model roster without merging identities",
          paragraphs: [
            "Agencies need repeatable operations, but copying one chatbot configuration across every model produces the same personality with different names. Each creator needs independent identity, boundaries, schedule, media, voice and fan memories.",
            "Telepipe keeps those records separate and exposes status, usage and pause controls per model. Begin with one constrained model, review conversations and only then replicate the operating process across the roster.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/ai-chatbot-for-creators",
          label: "For creators",
          description: "Keep one creator identity available without living in the inbox.",
        },
        {
          href: "/ai-chatbot-for-model-agencies",
          label: "For agencies",
          description: "Manage multiple separated model workspaces from one dashboard.",
        },
        {
          href: "/fanvue-ai-chatbot",
          label: "Fanvue AI chatbot",
          description: "See the subscription-side conversation workflow.",
        },
      ]}
      ctaTitle="Give one virtual creator a consistent conversation layer."
      ctaBody="Define the model identity, connect the authorized channels and review the workflow before adding the next creator."
      ctaNote="Separate model workspaces · Approved assets · Human-owned controls"
    />
  );
}

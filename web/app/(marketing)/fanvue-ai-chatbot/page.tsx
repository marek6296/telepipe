import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "Fanvue AI Chatbot for Creator DMs",
  description:
    "Handle Fanvue creator DMs with a persistent AI persona, fan memory, approved photos and links, conversation review and agency-level controls.",
  path: "/fanvue-ai-chatbot",
});

const FAQ = [
  {
    q: "What does the Telepipe Fanvue AI chatbot handle?",
    a: "It uses the configured model persona and conversation context for Fanvue DMs while keeping chats, approved photos, settings and the creator link visible to the operator.",
  },
  {
    q: "Does the chatbot remember each Fanvue subscriber?",
    a: "Conversation context and useful fan memory remain attached to the correct model and fan so later replies can continue earlier topics.",
  },
  {
    q: "Can it send any photo automatically?",
    a: "No unrestricted library is assumed. Operators upload and organize approved model photos and remain responsible for the rights, consent and rules attached to them.",
  },
  {
    q: "Can I review Fanvue conversations?",
    a: "Yes. Fanvue chat views remain available in the model workspace so operators can inspect conversations and refine the model settings.",
  },
  {
    q: "Is Telepipe affiliated with Fanvue?",
    a: "Telepipe is an independent creator-automation product. Fanvue is a third-party platform with its own terms, availability and product rules.",
  },
];

export default function FanvueAiChatbotPage() {
  return (
    <SeoPage
      path="/fanvue-ai-chatbot"
      eyebrow="Fanvue AI chatbot"
      title="Fanvue conversations with one persistent persona."
      dim="Memory and operator control included."
      lead="Telepipe brings the model profile, fan context, approved assets and conversation review into one workspace for creators and agencies operating Fanvue DMs."
      highlights={[
        {
          title: "Subscriber continuity",
          body: "Earlier topics and useful fan facts remain connected to the correct Fanvue conversation and model.",
        },
        {
          title: "Approved creator assets",
          body: "Photos and the creator's Fanvue link live in the model workspace instead of being invented by a generic chatbot.",
        },
        {
          title: "Visible conversations",
          body: "Operators can inspect chats, change model rules and pause the workflow when human judgment is needed.",
        },
      ]}
      sections={[
        {
          title: "What a Fanvue AI chatbot needs beyond auto-messages",
          paragraphs: [
            "A welcome message can start a conversation, but ongoing subscriber DMs quickly require identity consistency and memory. The chatbot needs to know which creator it represents, what the fan already discussed and which content or link is approved for use.",
            "Telepipe combines the model's identity, behavior and daily-life configuration with the context of the Fanvue chat. That produces a repeatable operating layer rather than a collection of disconnected generated messages.",
          ],
        },
        {
          title: "Preserve the creator persona across Telegram and Fanvue",
          paragraphs: [
            "Creators may talk with an audience on Telegram while using Fanvue for the subscription relationship. Running unrelated prompts for each channel makes the same model sound like different people.",
            "Telepipe keeps both channel settings inside one model workspace. The conversations remain inspectable by channel, while the structured persona provides a consistent foundation for the represented creator.",
          ],
          points: [
            "One structured model identity",
            "Separate conversations per fan",
            "Telegram and Fanvue workspaces",
            "Per-model status and pause controls",
          ],
        },
        {
          title: "Use fan memory without mixing subscribers",
          paragraphs: [
            "Useful memory can include names, preferences, earlier topics and promises that make a later conversation coherent. It must remain scoped to the correct fan and must not leak between models in an agency account.",
            "Telepipe attaches memory to the model and conversation identity. Operators should still collect only the context they need and apply appropriate privacy and retention practices to their creator business.",
          ],
        },
        {
          title: "Keep media and conversion actions constrained",
          paragraphs: [
            "Fanvue creator conversations often involve media and a clear next step. A safe workflow uses approved photo sets and a verified creator link instead of letting the chatbot invent uploads, offers or destinations.",
            "Telepipe exposes those assets and settings in the dashboard. The creator or agency remains responsible for content rights, consent, pricing, Fanvue terms and every business rule the model is configured to follow.",
          ],
        },
        {
          title: "Review quality before scaling the roster",
          paragraphs: [
            "Start with one model and a constrained conversation scope. Review real Fanvue chats, identify exceptions and update the persona or boundaries before relying on the same operating process for additional creators.",
            "AI can provide repeatable coverage, but humans remain accountable for policy, identity changes, sensitive situations and quality decisions. Immediate pause and visible chat history keep that accountability practical.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/ai-model-chatbot",
          label: "AI model chatbot",
          description: "Build the persistent character behind each channel.",
        },
        {
          href: "/ai-chatbot-for-creators",
          label: "For creators",
          description: "See how one creator can keep conversations moving.",
        },
        {
          href: "/ai-chatbot-for-model-agencies",
          label: "For agencies",
          description: "Operate multiple independent creator workspaces.",
        },
      ]}
      ctaTitle="Connect Fanvue conversations to the model behind them."
      ctaBody="Configure one creator, review the chats and keep the approved identity, assets and limits visible to the operator."
      ctaNote="Independent product · Human-owned settings · Pause any time"
    />
  );
}

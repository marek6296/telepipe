import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Chatbot for Model Agencies",
  description:
    "Manage multiple creator personas, Telegram and Fanvue conversations, voice settings and usage from one AI chatbot workspace built for model agencies.",
  path: "/ai-chatbot-for-model-agencies",
});

const FAQ = [
  {
    q: "Can an agency manage more than one model?",
    a: "Yes. Each model has a separate identity, memory, Telegram connection, Fanvue configuration, voice and status inside the same workspace.",
  },
  {
    q: "Are persona settings shared between models?",
    a: "No. A model's profile and conversation data stay attached to that model so one identity does not bleed into another.",
  },
  {
    q: "Can individual models be paused?",
    a: "Yes. The dashboard supports model-level status controls, allowing an operator to pause one model without stopping the rest of the roster.",
  },
  {
    q: "Can an agency see usage by model?",
    a: "The dashboard includes account and model usage views so operators can understand where replies and spend are occurring.",
  },
  {
    q: "Do we need separate automation servers?",
    a: "No. Telegram connection, persona configuration, memory and the supported Fanvue tools are managed through the Telepipe web application.",
  },
];

export default function AiChatbotForModelAgenciesPage() {
  return (
    <SeoPage
      path="/ai-chatbot-for-model-agencies"
      eyebrow="For agencies"
      title="An AI chatbot for model agencies."
      dim="One workspace, separate identities."
      lead="Operate multiple creator personas without mixing their voices, memories or account settings. Each model stays distinct while the agency keeps one operational view."
      highlights={[
        {
          title: "One profile per model",
          body: "Identity, behavior, schedule, media, voice and connections remain separated by model.",
        },
        {
          title: "Roster-level visibility",
          body: "See model status and usage from the workspace, then open the exact model that needs attention.",
        },
        {
          title: "Operational controls",
          body: "Pause models individually, protect Telegram contacts and update live configuration without rebuilding a stack.",
        },
      ]}
      sections={[
        {
          title: "Why agency automation fails when every model shares one prompt",
          paragraphs: [
            "An agency roster is not one character with different account names. Each creator needs her own facts, boundaries, texting rhythm, daily life, voice and conversion rules.",
            "Telepipe keeps those controls in separate model workspaces. Conversation memory is also tied to the correct model and fan, reducing the risk of context moving between unrelated identities.",
          ],
        },
        {
          title: "A repeatable operating system for every new model",
          paragraphs: [
            "The same guided workflow can be used to connect Telegram, build a persona, organize photos, configure voice and add Fanvue settings. The structure repeats; the content and identity do not.",
            "That gives an agency a consistent onboarding process without forcing every creator into the same voice.",
          ],
          points: [
            "Separate encrypted connections",
            "Per-model persona and memory",
            "Per-model photo and voice settings",
            "Independent pause state",
          ],
        },
        {
          title: "See what is active before opening every inbox",
          paragraphs: [
            "The workspace sidebar and model list expose model state at a glance. Usage dashboards summarize replies, conversations and spend before the operator drills into an individual Telegram or Fanvue area.",
            "That makes exception handling easier: the agency can focus human attention on setup, unusual conversations and model changes instead of treating every reply as manual work.",
          ],
        },
        {
          title: "A shared balance with visible consumption",
          paragraphs: [
            "Pipe Coins provide one account balance while usage remains measurable across the work being done. Top-ups do not expire, and models pause when the balance reaches zero rather than creating an uncontrolled invoice.",
            "For agencies, that connects operating volume to actual use instead of charging a fixed subscription for every model regardless of inbox activity.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/alternatives/botly-alternative",
          label: "Botly alternative",
          description: "Per-model personas, control bots and no agency tier.",
        },
        {
          href: "/ai-chatbot-for-creators",
          label: "For individual creators",
          description: "A focused view of the workflow for one creator identity.",
        },
        {
          href: "/telegram-ai-chatbot",
          label: "Telegram AI chatbot",
          description: "Understand the connected Telegram agent and its controls.",
        },
        {
          href: "/pricing",
          label: "Usage pricing",
          description: "Compare Pipe Coin packs and measured reply estimates.",
        },
      ]}
      ctaTitle="Build a cleaner operation for every model in the roster."
      ctaBody="Start with one model, validate the workflow and add the rest without creating separate automation infrastructure."
      ctaNote="One workspace · Separate model identities · Usage-based billing"
    />
  );
}

import type { Metadata } from "next";

import { CinematicHero } from "@/components/landing/cinematic-hero";
import { marketingMetadata, SITE_URL, structuredData } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Telegram Chatbot for Creators & Agencies",
  description:
    "An AI agent that answers your Telegram and Fanvue DMs — in your own name or as a persona you create, with AI voice notes and your photos. Built for creators and model agencies.",
  path: "/",
});

const HOME_SCHEMA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: "Telepipe",
      url: SITE_URL,
      logo: `${SITE_URL}/logo-white.png`,
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: "Telepipe",
      publisher: { "@id": `${SITE_URL}/#organization` },
      inLanguage: "en",
    },
    {
      "@type": "SoftwareApplication",
      "@id": `${SITE_URL}/#software`,
      name: "Telepipe",
      url: SITE_URL,
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      description:
        "An AI agent that replies to Telegram and Fanvue direct messages on behalf of a creator or a persona they define, including AI-generated voice notes and photos from their own library.",
      featureList: [
        "AI agent replying on your behalf or as a persona you define",
        "Telegram and Fanvue direct message automation",
        "AI-generated voice notes",
        "Photos sent from your own library",
        "Per-persona languages, tone and boundaries",
        "Usage-based Pipe Coin billing",
      ],
      publisher: { "@id": `${SITE_URL}/#organization` },
    },
  ],
};

/**
 * Landing (`/`) — len kinematická scéna.
 *
 * Sekcie Features / How it works / Pricing sa presunuli na vlastné stránky
 * (`/features`, `/how-it-works`, `/pricing`), takže pod pinnutou scénou už nič
 * nie je — po dobehnutí timeline sa odopne pin a odkryje footer z layoutu.
 * Nav a footer poskytuje `app/(marketing)/layout.tsx`.
 */
export default function Home() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: structuredData(HOME_SCHEMA) }}
      />
      <CinematicHero />
    </>
  );
}

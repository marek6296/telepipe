import type { Metadata } from "next";

import { CinematicHero } from "@/components/landing/cinematic-hero";
import { marketingMetadata, SITE_URL, structuredData } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "AI Telegram Chatbot for Creators & Agencies",
  description:
    "Automate Telegram DMs with a persistent AI persona, human-like replies, voice messages and conversion-ready links. Built for creators and model agencies.",
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
        "AI chat automation for creators and model agencies using Telegram and Fanvue.",
      featureList: [
        "Persistent AI persona and conversation memory",
        "Telegram DM automation",
        "AI voice messages",
        "Fanvue chat automation",
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

import type { Metadata } from "next";

export const SITE_NAME = "Telepipe";
export const SITE_URL = "https://telepipe.me";

type MarketingMetadataInput = {
  title: string;
  description: string;
  path: `/${string}` | "/";
};

/**
 * Jediný zdroj canonical, Open Graph a Twitter metadát pre verejné stránky.
 * Relatívne URL sa opierajú o `metadataBase` v root layoute, ktorý musí vždy
 * ukazovať na ostrú doménu telepipe.me.
 */
export function marketingMetadata({
  title,
  description,
  path,
}: MarketingMetadataInput): Metadata {
  const socialTitle = `${title} | ${SITE_NAME}`;

  return {
    title,
    description,
    alternates: {
      canonical: path,
    },
    openGraph: {
      title: socialTitle,
      description,
      url: path,
      type: "website",
      siteName: SITE_NAME,
      locale: "en_US",
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description,
    },
  };
}

/** Bezpečná serializácia JSON-LD vloženého do HTML. */
export function structuredData(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

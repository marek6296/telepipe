import type { MetadataRoute } from "next";

import { ALTERNATIVE_SLUGS } from "@/lib/alternatives";
import { LEGAL_READY } from "@/lib/legal";
import { SITE_URL } from "@/lib/seo";

type PageEntry = {
  path: string;
  priority: number;
  changeFrequency: "weekly" | "monthly" | "yearly";
};

const PAGES: PageEntry[] = [
  { path: "/", priority: 1, changeFrequency: "weekly" },
  { path: "/telegram-ai-chatbot", priority: 0.95, changeFrequency: "monthly" },
  { path: "/telegram-automation", priority: 0.9, changeFrequency: "monthly" },
  { path: "/ai-chatter", priority: 0.9, changeFrequency: "monthly" },
  { path: "/ai-model-chatbot", priority: 0.88, changeFrequency: "monthly" },
  { path: "/fanvue-ai-chatbot", priority: 0.88, changeFrequency: "monthly" },
  { path: "/virtual-number-for-telegram", priority: 0.9, changeFrequency: "weekly" },
  { path: "/ai-chatbot-for-creators", priority: 0.85, changeFrequency: "monthly" },
  { path: "/ai-chatbot-for-model-agencies", priority: 0.85, changeFrequency: "monthly" },
  { path: "/features", priority: 0.8, changeFrequency: "monthly" },
  { path: "/how-it-works", priority: 0.8, changeFrequency: "monthly" },
  { path: "/pricing", priority: 0.8, changeFrequency: "monthly" },
  { path: "/guides", priority: 0.75, changeFrequency: "weekly" },
  {
    path: "/guides/automate-telegram-dms-with-ai",
    priority: 0.8,
    changeFrequency: "monthly",
  },
  {
    path: "/guides/telegram-virtual-number-verification",
    priority: 0.8,
    changeFrequency: "monthly",
  },
  {
    path: "/guides/ai-chatter-vs-human-chatter",
    priority: 0.8,
    changeFrequency: "monthly",
  },
];

/**
 * Porovnávacie stránky. Priorita je vysoká zámerne: kto hľadá „X alternative",
 * má najvyšší nákupný úmysel zo všetkých návštevníkov — už vie, čo chce.
 * Zoznam sa berie z `lib/alternatives.ts`, takže nová stránka je v sitemape
 * automaticky a nedá sa na ňu zabudnúť.
 */
const ALTERNATIVE_PAGES: PageEntry[] = [
  { path: "/alternatives", priority: 0.85, changeFrequency: "monthly" },
  ...ALTERNATIVE_SLUGS.map((slug) => ({
    path: `/alternatives/${slug}`,
    priority: 0.9,
    changeFrequency: "monthly" as const,
  })),
];

/**
 * Právne stránky pridávame do sitemapy až keď sú v `lib/legal.ts` skutočné
 * údaje prevádzkovateľa. Ponúkať vyhľadávačom Privacy Policy bez identifikácie
 * prevádzkovateľa by bolo horšie než ju neponúkať — je to presne tá vec, ktorú
 * hodnotiace automaty kontrolujú.
 */
const LEGAL_PAGES: PageEntry[] = LEGAL_READY
  ? [
      { path: "/contact", priority: 0.6, changeFrequency: "yearly" },
      { path: "/privacy", priority: 0.4, changeFrequency: "yearly" },
      { path: "/terms", priority: 0.4, changeFrequency: "yearly" },
    ]
  : [];

export default function sitemap(): MetadataRoute.Sitemap {
  return [...PAGES, ...ALTERNATIVE_PAGES, ...LEGAL_PAGES].map(({ path, priority, changeFrequency }) => ({
    url: `${SITE_URL}${path}`,
    lastModified: new Date(),
    changeFrequency,
    priority,
  }));
}

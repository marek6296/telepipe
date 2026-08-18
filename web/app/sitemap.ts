import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/seo";

const PAGES: Array<{
  path: string;
  priority: number;
  changeFrequency: "weekly" | "monthly";
}> = [
  { path: "/", priority: 1, changeFrequency: "weekly" },
  { path: "/telegram-ai-chatbot", priority: 0.95, changeFrequency: "monthly" },
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

export default function sitemap(): MetadataRoute.Sitemap {
  return PAGES.map(({ path, priority, changeFrequency }) => ({
    url: `${SITE_URL}${path}`,
    lastModified: new Date(),
    changeFrequency,
    priority,
  }));
}

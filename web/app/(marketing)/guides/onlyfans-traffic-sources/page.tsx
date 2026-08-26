import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "OnlyFans Traffic Sources That Still Work",
  description:
    "A grounded look at creator traffic sources — Reddit, Instagram, TikTok, Telegram and paid — what each one costs in time, and which ones you actually own.",
  path: "/guides/onlyfans-traffic-sources",
});

const FAQ = [
  {
    q: "What is the best traffic source for a creator page?",
    a: "There is no single best one. The useful question is which channel you own: a follower on a social platform can be removed by that platform, while a Telegram chat or an email address stays yours. Most stable operations mix a discovery channel with an owned one.",
  },
  {
    q: "Why does free social traffic convert so badly?",
    a: "Because it is a cold click. Someone who taps a bio link has no reason to pay yet. Traffic that passes through a conversation first converts better for the same reason a shop assistant beats a shelf.",
  },
  {
    q: "Is buying traffic worth it?",
    a: "It can be, but adult offers are restricted on most major ad networks and the workable placements are expensive. Paid traffic also amplifies whatever your funnel already does — if the middle is broken, you are paying to lose faster.",
  },
  {
    q: "How many followers do you need?",
    a: "Fewer than people assume, if the middle works. A small audience that ends up in a conversation outperforms a large one that only ever sees a link.",
  },
  {
    q: "How do you know which source is working?",
    a: "Give each source and each conversation its own link. Without that, every channel gets credit for whatever happened to arrive, and the one that actually pays is invisible.",
  },
];

export default function OnlyFansTrafficSourcesPage() {
  return (
    <SeoPage
      path="/guides/onlyfans-traffic-sources"
      eyebrow="Guide · Traffic"
      title="Creator traffic sources,"
      dim="and which ones you own."
      lead="Every list of traffic sources is the same five channels. The part that decides whether an account survives is not which channel you pick — it is whether the traffic ends up somewhere you control, and whether anything happens between the click and the paywall."
      highlights={[
        {
          title: "Rented vs owned",
          body: "Followers live on someone else's platform and can be gone in a morning. A conversation in a messenger is yours, and it is the only asset that survives a ban.",
        },
        {
          title: "Cold clicks convert cold",
          body: "A bio link asks a stranger to pay a stranger. A conversation first is what turns interest into a reason.",
        },
        {
          title: "Unmeasured traffic is a guess",
          body: "If every source shares one link, none of them can be judged. Per-source and per-conversation links cost nothing and settle the argument.",
        },
      ]}
      sections={[
        {
          title: "The channels, honestly",
          paragraphs: [
            "Each of these works for somebody. What differs is the price in hours, the risk of losing it overnight, and how warm the person is when they arrive.",
          ],
          points: [
            "Reddit — still the highest-intent free channel, and the most rule-bound. Every subreddit has its own verification and posting rules and enforces them harder than the platform does.",
            "Instagram — enormous reach, hostile to adult links. Works as discovery, not as a destination; the link in bio has to point somewhere neutral.",
            "TikTok — the fastest way to a large cold audience and the fastest way to lose the account. Treat any single account as temporary.",
            "X — permissive about adult content relative to the others, crowded, and effective mostly with an existing audience.",
            "Telegram — small reach on its own, but the only one on this list where a real conversation happens and where the audience is genuinely yours.",
            "Paid — restricted placements, high prices, and it multiplies whatever your funnel already does, in both directions.",
          ],
        },
        {
          title: "Discovery and ownership are two different jobs",
          paragraphs: [
            "The channels that find people are rarely the channels that keep them. Instagram and TikTok are good at being seen and bad at being owned; a messenger is the reverse.",
            "The pattern that survives is a pair: something public for discovery, and something private that the platform cannot take away. Discovery brings people in, the private channel holds them, and the paid page is where it ends.",
          ],
        },
        {
          title: "The middle is where the money goes missing",
          paragraphs: [
            "Most operators can name their traffic sources. Far fewer can say what happens after the click — and that gap is usually the whole problem.",
            "Someone lands, sees a paywall and leaves. Nothing about that is a traffic problem, but it looks exactly like one, so the response is usually to buy more traffic and lose it faster.",
          ],
          points: [
            "Click on the bio link — did they land anywhere with a person in it?",
            "First message — was there anything to answer, and did it answer like a person?",
            "The ask — did the link go out at a moment that made sense?",
            "The page — did it close what the conversation opened?",
          ],
        },
        {
          title: "What to measure before spending anything",
          paragraphs: [
            "Three numbers per source settle almost every argument about traffic: how many conversations it produced, how many of those reached the link, and how many opened it. Revenue is the fourth, and it is the least useful for diagnosis because it fails silently at every earlier step.",
            "The reason to measure the click specifically is that it separates two opposite failures. Nobody clicking means the conversation is not persuasive. Everybody clicking and nobody paying means the page is not. They look identical on a bank statement.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/guides/telegram-to-onlyfans-funnel",
          label: "The Telegram funnel",
          description: "What happens between the first DM and the first payment.",
        },
        {
          href: "/guides/how-to-get-fanvue-subscribers",
          label: "Getting Fanvue subscribers",
          description: "The same problem from the Fanvue side, including what happens after they pay.",
        },
        {
          href: "/ai-chatbot-for-creators",
          label: "For creators",
          description: "How the conversation half is run without a chatter team.",
        },
      ]}
      ctaTitle="Find out which half is broken."
      ctaBody="Every conversation gets its own link, so links sent, links opened and payments stop being one number."
      ctaNote="No card required · Usage-based Pipe Coins · Pause any time"
    />
  );
}

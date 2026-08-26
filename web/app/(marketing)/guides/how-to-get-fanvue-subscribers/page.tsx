import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "How to Get Fanvue Subscribers (and Keep Them)",
  description:
    "Where Fanvue traffic comes from, when to send the link, and why the first message after someone subscribes decides whether they ever spend again.",
  path: "/guides/how-to-get-fanvue-subscribers",
});

const FAQ = [
  {
    q: "How do people find a Fanvue page?",
    a: "Almost never by searching Fanvue. Discovery happens somewhere else — social, a messenger, a link in bio — and the page is the destination. Treat the page as the close, not the shop window.",
  },
  {
    q: "Does the subscription price matter much?",
    a: "Less than the reason to subscribe. A cheap page nobody has a reason to open earns nothing; most revenue on these platforms comes from what happens in the DMs afterwards, not from the subscription itself.",
  },
  {
    q: "What should the first message after a subscription say?",
    a: "It should sound like someone who knows who just arrived. A generic thank-you tells them the person they were talking to is gone, which is the fastest way to end the spending before it starts.",
  },
  {
    q: "How do you keep a subscriber spending?",
    a: "By making the conversation worth being in, and by offering content at moments that make sense rather than on a timer. Repeated offers with nothing between them read as a shop, and shops get muted.",
  },
  {
    q: "Can this be automated?",
    a: "The messaging can, within the platform's own rules, and Fanvue exposes an official API for it. Whether you keep a human on the send button is a setting, not a limitation — many operators approve replies at first and loosen it later.",
  },
];

export default function HowToGetFanvueSubscribersPage() {
  return (
    <SeoPage
      path="/guides/how-to-get-fanvue-subscribers"
      eyebrow="Guide · Fanvue"
      title="Getting Fanvue subscribers,"
      dim="and what happens after."
      lead="Subscriber count is the metric everyone optimises and the one that explains the least. What decides whether a Fanvue page earns is narrower: whether people arrive with a reason, and whether the first message after they pay sounds like the person they were already talking to."
      highlights={[
        {
          title: "Nobody browses Fanvue",
          body: "Discovery happens elsewhere. The page converts attention you already earned somewhere else, so the work is upstream of it.",
        },
        {
          title: "The subscription is the start of the bill",
          body: "On platforms like this, most of the money arrives after the subscription, in the DMs. A page with subscribers and a dead inbox is a page that earned once.",
        },
        {
          title: "Continuity is the whole trick",
          body: "If the person who subscribed after a week of conversation is greeted as a stranger, the week is wasted. Carrying that history across is worth more than any welcome discount.",
        },
      ]}
      sections={[
        {
          title: "Before the subscription: give them something to subscribe to",
          paragraphs: [
            "A link on its own asks a stranger to pay a stranger. The conversion problem is almost never the price — it is that nothing between the click and the paywall gave anyone a reason.",
            "The reliable version is a conversation first, somewhere free, where a person answers like a person. The link then answers a question they already asked, which is a completely different thing from an advert.",
          ],
          points: [
            "Send the link once, at the moment it answers something",
            "Say what is on the other side, not just where it is",
            "Then remind rather than resend — repetition is what reads as automation",
          ],
        },
        {
          title: "The first message after they pay",
          paragraphs: [
            "This is the message most operations get wrong, because it is usually written by a different system — or a different person — than the one that earned the subscription.",
            "Someone who spent a week talking on a messenger and then subscribes should be met by someone who knows their name, their job, and what they were joking about yesterday. The alternative is a welcome template, which tells them the conversation they were in is over.",
          ],
        },
        {
          title: "After that: selling without becoming a shop",
          paragraphs: [
            "The revenue on a creator page comes from content offered at moments that make sense, not from a schedule. A few rules do most of the work here, and all of them are about restraint.",
          ],
          points: [
            "Nothing offered until the conversation has actually started",
            "Never two offers in a row, and never while an earlier one sits unopened",
            "Never describe content that does not exist — a broken promise is remembered",
            "When somebody buys, the thank-you is a message, not the next pitch",
          ],
        },
        {
          title: "What to watch",
          paragraphs: [
            "Subscriber count answers a vanity question. Three other numbers answer a useful one: how many conversations reached the link, how many opened it, and how much each subscriber spent after the first payment.",
            "The gap between the second and the third is where a page either becomes a business or stays a hobby, and it is decided almost entirely in the inbox.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/fanvue-ai-chatbot",
          label: "Fanvue AI chatbot",
          description: "How the Fanvue side is run, including who the fan was before they paid.",
        },
        {
          href: "/guides/telegram-to-onlyfans-funnel",
          label: "The funnel, measured",
          description: "What happens between the first DM and the first payment.",
        },
        {
          href: "/guides/onlyfans-traffic-sources",
          label: "Traffic sources",
          description: "Where the people at the top of this actually come from.",
        },
      ]}
      ctaTitle="Keep the conversation across the paywall."
      ctaBody="One persona on Telegram and Fanvue, with the fan's history carried over so the first paid message is not a cold start."
      ctaNote="No card required · Usage-based Pipe Coins · Pause any time"
    />
  );
}

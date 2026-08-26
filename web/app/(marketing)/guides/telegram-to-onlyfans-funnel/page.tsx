import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "Telegram to OnlyFans Funnel: How It Actually Works",
  description:
    "How a Telegram DM turns into a paying subscriber — the handover, when the link goes out, and the three numbers that tell you which half of the funnel is broken.",
  path: "/guides/telegram-to-onlyfans-funnel",
});

const FAQ = [
  {
    q: "Why route traffic through Telegram instead of straight to the page?",
    a: "A cold link converts on impulse alone. A conversation first gives someone a reason to click, and it gives you a channel you own — a Telegram chat survives a platform ban in a way a bio link does not.",
  },
  {
    q: "When should the link go out?",
    a: "When the conversation has earned it — usually once he asks for something the free channel cannot give him. Sending it in the first message is the fastest way to be ignored, and sending it repeatedly reads as an advert.",
  },
  {
    q: "How many times should you send the link?",
    a: "Once. After that, remind him it is above in the conversation. Resending the same link makes the chat look automated, which is exactly the impression the whole approach is trying to avoid.",
  },
  {
    q: "How do you know if the funnel is broken at the top or the bottom?",
    a: "Measure clicks. Nobody clicking is a conversation problem. Everybody clicking and nobody paying is a page problem. Without that split you end up rewriting whichever one you guessed.",
  },
  {
    q: "Is automating Telegram DMs allowed?",
    a: "Telegram has its own terms and paid platforms have theirs, and following them is the operator's responsibility. Practical safety comes from behaving like an account, not a broadcaster: daily caps, active hours, human pacing and never messaging strangers unprompted.",
  },
];

export default function TelegramToOnlyFansFunnelPage() {
  return (
    <SeoPage
      path="/guides/telegram-to-onlyfans-funnel"
      eyebrow="Guide · Funnel"
      title="The Telegram to OnlyFans funnel,"
      dim="measured instead of guessed."
      lead="Most creator funnels are described as a diagram and run as a hope. This is the same funnel with numbers attached: what happens between the first DM and the first payment, and where it actually leaks."
      highlights={[
        {
          title: "Four steps, three of them free",
          body: "Someone writes, a conversation happens, a link goes out, a payment lands. Only the last step involves the paid platform at all — which is why the first three are where the money is won or lost.",
        },
        {
          title: "The link is a moment, not a message",
          body: "It goes out once, when the conversation has earned it. Everything after that is a reminder that it is already above, not another copy of it.",
        },
        {
          title: "Two failures look identical",
          body: "Zero revenue looks the same whether nobody clicked or everybody clicked and left. They need opposite fixes, so the click has to be measured.",
        },
      ]}
      sections={[
        {
          title: "Step one: the conversation has to be worth having",
          paragraphs: [
            "The first messages decide everything after them. Somebody who writes to a creator account is testing whether there is a person there, and the tells are not the words — they are the timing, the consistency and the memory.",
            "A reply that lands in three seconds at four in the morning is a bot. A reply that contradicts what was said an hour ago is a bot. A compliment that arrives twice in the same wording is a bot. None of that is fixed by better copywriting; it is fixed by giving the account a day, a memory and a pace.",
          ],
          points: [
            "Replies take as long as replies take, and vary by what she is doing",
            "What she said earlier stays true later",
            "Names, jobs, timezones and running jokes are remembered",
            "Nothing is promised that cannot be delivered",
          ],
        },
        {
          title: "Step two: the handover",
          paragraphs: [
            "The link should answer a question he already asked. The natural moment is when he wants something the free channel does not carry — more explicit conversation, photos, or simply more of her attention than a busy inbox can give.",
            "Send it once. Then, if it comes up again, point at it rather than resending it: it is already in the conversation, and saying so sounds like a person while resending sounds like a funnel.",
          ],
        },
        {
          title: "Step three: the number nobody has",
          paragraphs: [
            "Give every conversation its own short link. It costs nothing and it converts a guess into a fact: a click identifies the person who opened the page, and the gap between links sent and links opened is the single most useful number in the whole operation.",
            "In one account we measured, thirteen links went out and three were opened. That is not a page problem — the page was barely seen. Rewriting the sales copy would have been a month spent on the wrong half.",
          ],
          points: [
            "Links sent — how often the conversation reached the ask",
            "Links opened — whether the ask was persuasive",
            "Payments — whether the page closes what the chat opened",
          ],
        },
        {
          title: "Step four: closing the loop",
          paragraphs: [
            "When a payment arrives it should be traceable back to the conversation that produced it. Otherwise the person who subscribes becomes a stranger on the paid platform, and the first message there sounds like meeting someone new — after a week of talking.",
            "It is also the only way to know which conversations are worth having. Without attribution, every chat looks equally valuable, which means none of them can be improved on purpose.",
          ],
        },
        {
          title: "What breaks it",
          paragraphs: [
            "Three things end this funnel faster than anything else, and all three are self-inflicted.",
          ],
          points: [
            "Sending the link too early, before there is a reason to click",
            "Repeating the link until the chat reads as an advert",
            "Promising content that does not exist — the one mistake a fan remembers",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/guides/onlyfans-traffic-sources",
          label: "Where the traffic comes from",
          description: "The channels that actually feed a creator funnel, and what each one costs.",
        },
        {
          href: "/alternatives/onlyfans-ai-chatter-alternative",
          label: "AI chatter alternative",
          description: "Why chatter tools cover the second half of this funnel, not the first.",
        },
        {
          href: "/telegram-ai-chatbot",
          label: "Telegram AI chatbot",
          description: "How the conversation side is actually run.",
        },
      ]}
      ctaTitle="Put a number on your own funnel."
      ctaBody="Connect a model, let her talk, and watch links sent, links opened and payments land in the same view."
      ctaNote="No card required · Usage-based Pipe Coins · Pause any time"
    />
  );
}

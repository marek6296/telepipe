/**
 * Stránky „X alternative" — najvyšší nákupný úmysel, aký vo vyhľadávaní je.
 *
 * Kto hľadá „supercreator alternative", už vie, čo chce, a už za to niekomu
 * platí alebo sa chystá. Preto sú tieto stránky oddelené od bežných keyword
 * landingov: nevysvetľujú, čo je AI chatter, ale rovno rozdiel.
 *
 * TRI PRAVIDLÁ, KTORÉ TU PLATIA BEZ VÝNIMKY
 * -----------------------------------------
 * 1. **O konkurencii len to, čo je verejné a overiteľné.** Žiadne ceny do
 *    textu (menia sa a zajtra by sme klamali), žiadne „nefunguje", žiadne
 *    vymyslené funkcie. Ich pozíciu opisujeme kategóriou, nie posudkom.
 * 2. **Rozdiel, nie osočovanie.** Google aj čitateľ rozoznajú útok od
 *    porovnania a útok nekonvertuje. Píše sa, čo robíme MY inak.
 * 3. **Vlastníctvo značky sa prizná.** Na každej stránke je veta, že názov
 *    patrí jeho majiteľovi a že s ním nie sme spojení. Bez toho je to
 *    problém, ktorý nemá s SEO nič spoločné.
 *
 * Tenkým doorway stránkam bráni to, že každý záznam má vlastné sekcie a
 * vlastné FAQ — nie vymenené kľúčové slovo v tej istej vete.
 */

export type AlternativeFaq = { q: string; a: string };

export type AlternativeSection = {
  title: string;
  paragraphs: string[];
  points?: string[];
};

export type Alternative = {
  /** URL kúsok: `/alternatives/<slug>`. */
  slug: string;
  /** Ako sa produkt volá u nich — presne, aj s veľkými písmenami. */
  name: string;
  /** Do `<title>`. Krátke, lebo Google reže okolo 60 znakov. */
  title: string;
  description: string;
  /** Jedna veta nad nadpisom. */
  eyebrow: string;
  /** Čo to je — kategória, nie posudok. */
  lead: string;
  highlights: { title: string; body: string }[];
  sections: AlternativeSection[];
  faq: AlternativeFaq[];
};

/** Veta o vlastníctve značky. Rovnaká všade, aby sa nedala zabudnúť. */
export function trademarkNote(name: string): string {
  return (
    `${name} is a trademark of its respective owner. Telepipe is an independent ` +
    `product and is not affiliated with, endorsed by or sponsored by ${name}. ` +
    `Product details change — check their site for what they offer today.`
  );
}

/**
 * Čím sa Telepipe naozaj líši. Opakuje sa naprieč stránkami zámerne: je to
 * jedna vec a nemá zmysel ju na každej stránke prerozprávať inak.
 */
const ROZDIEL = {
  telegram:
    "Telepipe runs her actual Telegram account through Telegram's own client, " +
    "so the funnel starts before anyone has subscribed to anything. Most " +
    "chatter tools only reach people who already found the paid page.",
  window:
    "Every conversation has a window in days. Day one is the liveliest, then " +
    "it tapers, then she sends one last message pointing at her page and goes " +
    "quiet for good — no replies, no read receipts.",
  day:
    "She has a day. A schedule decides where she is hour by hour, so replies " +
    "arrive at gym speed from the gym and couch speed from the couch, and she " +
    "never contradicts herself about where she is.",
  coins:
    "There is no subscription and no seat. You buy Pipe Coins and spend them " +
    "as your models work — every reply, transcription and voice second metered " +
    "to the coin.",
};

export const ALTERNATIVES: Alternative[] = [
  {
    slug: "supercreator-alternative",
    name: "Supercreator",
    title: "Supercreator Alternative for Creator DMs",
    description:
      "Looking for a Supercreator alternative? Telepipe runs the model's own Telegram account, keeps a real daily schedule and bills per reply instead of per month.",
    eyebrow: "Supercreator alternative",
    lead:
      "Supercreator is a creator-messaging suite that works inside the paid platform's own inbox. Telepipe sits one step earlier: it runs her Telegram account, holds the conversation like a person, and sends people to the paid page.",
    highlights: [
      {
        title: "Starts before the subscription",
        body: ROZDIEL.telegram,
      },
      {
        title: "Pay per reply, not per month",
        body: ROZDIEL.coins,
      },
      {
        title: "She has a day, not a shift",
        body: ROZDIEL.day,
      },
    ],
    sections: [
      {
        title: "The difference is where the conversation happens",
        paragraphs: [
          "Chatter suites are built around the inbox of the paid platform. That is the right place to answer someone who already paid, and the wrong place to meet someone who never heard of her.",
          "Telepipe answers on Telegram from her own account, using Telegram's normal client — the same app her audience already has open. The paid page is where the conversation goes, not where it starts.",
        ],
        points: [
          "Telegram DMs from her own account, not a bot handle",
          "Fanvue DMs through the official Fanvue API",
          "Instagram DMs prepared for the same persona",
        ],
      },
      {
        title: "What stops it from reading like a bot",
        paragraphs: [
          "Anyone can bolt a language model onto an inbox. What gives it away is everything around the words: replies that land in three seconds at four in the morning, a photo promised and never sent, the same compliment twice, a story about the gym at the same minute as a story about the café.",
          "Telepipe decides those things in code, not in the prompt, because a prompt can be talked out of them.",
        ],
        points: [
          "A daily schedule sets where she is and how fast she answers from there",
          "Photos come from albums that match where she is, one album per chat",
          "She never promises content she does not have",
          "Voice notes are generated for what was actually said",
        ],
      },
      {
        title: "What you keep control of",
        paragraphs: [
          "Semi-automatic mode sends every draft to your own Telegram bot before it goes out. Three different replies to choose from, or write your own, or hand her a topic in your language and let her say it in hers.",
          "You can also open any chat from the menu and write into it yourself, send a photo, or take the conversation over entirely.",
        ],
      },
    ],
    faq: [
      {
        q: "Is Telepipe a Supercreator replacement?",
        a: "They solve different halves of the same funnel. Supercreator works inside the paid platform's inbox; Telepipe works on Telegram, Fanvue and Instagram to bring people there and keep them talking. Plenty of operators would run both.",
      },
      {
        q: "Does Telepipe charge per creator or per seat?",
        a: "Neither. There are no plans and nothing renews — you buy Pipe Coins and spend them as your models work. Running one model or ten changes the coins you spend, not a plan.",
      },
      {
        q: "Do I need a Chrome extension?",
        a: "No. Telepipe runs on our servers and connects to Telegram, Fanvue and Instagram directly. Nothing has to stay open on your machine.",
      },
      {
        q: "Can I read what she wrote?",
        a: "Yes. Every conversation is visible in the workspace, and the control bot can show you who a person is, what they talked about and where they are in the funnel before you reply.",
      },
    ],
  },
  {
    slug: "botly-alternative",
    name: "Botly",
    title: "Botly Alternative for Agencies and Creators",
    description:
      "A Botly alternative that runs the model's own Telegram account, keeps her schedule consistent, and bills per reply instead of a monthly agency tier.",
    eyebrow: "Botly alternative",
    lead:
      "Botly is an AI chat assistant for creator inboxes, aimed largely at agencies managing several creators. Telepipe is built around the same problem from the other end: the traffic that has not subscribed yet.",
    highlights: [
      {
        title: "One workspace, many models",
        body:
          "Each model is her own persona, her own schedule, her own albums and her own control bot. Nothing is shared between them by accident.",
      },
      { title: "No agency tier", body: ROZDIEL.coins },
      { title: "Conversations that end", body: ROZDIEL.window },
    ],
    sections: [
      {
        title: "Built for more than one model from the first day",
        paragraphs: [
          "Telepipe was multi-tenant before it had a landing page. A model is a row, not an install: her Telegram session, her Fanvue token, her persona and her photo albums belong to her and to nobody else in the account.",
          "Each model also gets her own control bot in Telegram, so whoever runs her does not need access to the whole workspace.",
        ],
        points: [
          "Per-model personas, schedules, albums and voices",
          "Per-model control bot with its own notifications",
          "Per-model reply mode: off, automatic or semi-automatic",
        ],
      },
      {
        title: "Where the money actually leaks",
        paragraphs: [
          "Most creator funnels do not lose people in the inbox. They lose them between the DM and the paid page, and nobody can say where because nothing is measured.",
          "Telepipe gives every conversation its own short link, so a click tells you exactly who opened the page. When a payment lands, it is matched back to the person she was talking to.",
        ],
        points: [
          "Per-conversation link, so clicks are attributable",
          "Payments matched back to the Telegram chat they came from",
          "A funnel view: talking, link sent, opened, paid",
        ],
      },
      {
        title: "Approval when you want it",
        paragraphs: [
          "Semi-automatic mode puts a card in your Telegram with three different replies — not three versions of one sentence — plus the option to regenerate, to hand her a topic in your own words, or to see who this person is before you decide.",
          "If nobody decides within the time you set, the first suggestion goes out on its own so the fan is not left waiting.",
        ],
      },
    ],
    faq: [
      {
        q: "Does Telepipe work for agencies with several creators?",
        a: "Yes. Models are separate from the first day: separate personas, schedules, albums, control bots and reply modes inside one workspace.",
      },
      {
        q: "How is billing handled across models?",
        a: "Pipe Coins sit on the account and every model spends from the same balance. There is no per-creator plan, so adding a model does not add a subscription.",
      },
      {
        q: "Can different people run different models?",
        a: "Each model has her own control bot in Telegram, so whoever runs her can work from that chat without being given the whole workspace.",
      },
      {
        q: "What happens when a conversation goes cold?",
        a: "Every chat has a window in days. It tapers, then she sends one last message pointing at her page and stops replying — she does not keep messaging someone who stopped answering.",
      },
    ],
  },
  {
    slug: "chatpersonas-alternative",
    name: "ChatPersonas",
    title: "ChatPersonas Alternative with a Real Daily Schedule",
    description:
      "A ChatPersonas alternative for creator DMs: one persona across Telegram, Fanvue and Instagram, with a schedule that keeps her story consistent.",
    eyebrow: "ChatPersonas alternative",
    lead:
      "ChatPersonas is an AI messaging tool for creator inboxes. Telepipe treats the persona as a person with a day, and carries that same person across Telegram, Fanvue and Instagram.",
    highlights: [
      { title: "One persona, three places", body: ROZDIEL.telegram },
      { title: "A schedule, not a mood", body: ROZDIEL.day },
      {
        title: "Memory that stays attached",
        body:
          "Facts, running topics and the tone of the conversation stay with the fan, so a reply next week can pick up what he said last week.",
      },
    ],
    sections: [
      {
        title: "A persona is not a paragraph",
        paragraphs: [
          "A personality prompt gets you a voice for about ten messages. After that the cracks show: she is at the gym and in a café in the same hour, she forgets the name she was told, she promises a photo that never arrives.",
          "Telepipe keeps the persona in the prompt and the reality in code. Where she is, how fast she answers, what she can send and what she already said are decided before the model writes a word.",
        ],
      },
      {
        title: "The same woman on every platform",
        paragraphs: [
          "The persona is written once. Telegram uses it to build a conversation and point at the paid page; Fanvue uses it with the fan who already paid and knows her; Instagram uses it under Instagram's rules, where paid links are never mentioned.",
          "On Fanvue she can also be told who this person was on Telegram, so the first message there does not sound like meeting a stranger.",
        ],
      },
      {
        title: "What she is not allowed to do",
        paragraphs: [
          "A universal human layer sits above whatever the persona says. It exists because a client can configure a persona badly and the result should still behave like a person.",
        ],
        points: [
          "No exclamation marks, no wall of text, no repeated compliment",
          "No promising content that is not in the library",
          "No pretending to know something she was never told",
          "No mentioning a paid platform on Instagram",
        ],
      },
    ],
    faq: [
      {
        q: "Can one persona work on more than one platform?",
        a: "Yes. The persona is written once and used on Telegram, Fanvue and Instagram, with the rules of each platform applied on top of it.",
      },
      {
        q: "How does she remember a fan?",
        a: "Facts and a running summary of the conversation stay attached to that fan, so later replies continue earlier topics instead of starting over.",
      },
      {
        q: "Can I write the persona myself?",
        a: "Yes, and there is a builder that will draft it from a few answers if you would rather start from something. Every field stays editable.",
      },
      {
        q: "What language does she write in?",
        a: "Whatever you set as her main language, with the languages she is supposed to know handled separately. If a fan writes in one of those, she can answer in it.",
      },
    ],
  },
  {
    slug: "onlyfans-ai-chatter-alternative",
    name: "OnlyFans AI chatter tools",
    title: "OnlyFans AI Chatter Alternative — Start on Telegram",
    description:
      "Most OnlyFans AI chatter tools only reach fans who already subscribed. Telepipe runs the model's Telegram account so the funnel starts earlier.",
    eyebrow: "AI chatter alternative",
    lead:
      "Chatter tools live inside the paid platform's inbox, usually through a browser extension. That covers the half of the funnel that already paid. Telepipe covers the half before it.",
    highlights: [
      { title: "The traffic problem, not the inbox problem", body: ROZDIEL.telegram },
      { title: "Measured, not guessed", body:
        "Every conversation gets its own short link, so you can tell the difference between nobody clicking and everybody clicking and not buying — two opposite problems." },
      { title: "Pay for what she sends", body: ROZDIEL.coins },
    ],
    sections: [
      {
        title: "Two halves of one funnel",
        paragraphs: [
          "A creator funnel has two halves. The first is turning a stranger into someone who clicks the link. The second is turning a subscriber into someone who spends. Chatter tools are built for the second half and are good at it.",
          "The first half is usually a person doing it by hand in Telegram, or nobody doing it at all. That is the half Telepipe automates — and it is the half where the traffic dies.",
        ],
      },
      {
        title: "How the handover works",
        paragraphs: [
          "She talks on Telegram like a person: her own account, her own day, replies that take as long as replies take. When the moment is right she sends the link — once per chat, with a reminder later if it is needed, never in every second message.",
          "The link is unique to that conversation, so the click tells you who opened the page. If a payment follows, it is matched back to the person she was talking to and she knows on Fanvue who she is talking to.",
        ],
        points: [
          "One link per conversation, so clicks are attributable",
          "The link goes out once, then reminders — not repetition",
          "Payments matched back to the Telegram chat",
        ],
      },
      {
        title: "Compliance is your call, and it stays visible",
        paragraphs: [
          "Paid platforms have their own rules about automation, and those rules are yours to follow. Telepipe gives every channel three modes — off, automatic and semi-automatic — so you can keep a human on the send button wherever you need one, and read everything that went out either way.",
        ],
      },
    ],
    faq: [
      {
        q: "Does Telepipe replace an OnlyFans chatter tool?",
        a: "Not exactly. Chatter tools work the inbox of the paid platform; Telepipe works Telegram, Fanvue and Instagram to fill it. Many operators would run both.",
      },
      {
        q: "Do I need a browser extension?",
        a: "No. Telepipe runs on our servers and connects directly, so nothing needs to stay open on your machine.",
      },
      {
        q: "Can I keep a human on the send button?",
        a: "Yes. Semi-automatic mode sends every draft to your own Telegram bot with three replies to choose from, and nothing goes out until you pick — or until the time limit you set, if you want one.",
      },
      {
        q: "How much does it cost?",
        a: "There is no subscription. You buy Pipe Coins and spend them per reply, so the bill follows the work rather than the calendar.",
      },
    ],
  },
  {
    slug: "cupidbot-alternative",
    name: "CupidBot",
    title: "CupidBot Alternative? Read This First",
    description:
      "CupidBot automates your own dating apps. Telepipe runs a creator's Telegram and Fanvue DMs. Here is the difference, so you land in the right place.",
    eyebrow: "CupidBot alternative",
    lead:
      "These two get searched together and they do opposite jobs. CupidBot is aimed at someone automating their own dating apps. Telepipe is for someone running a creator account and the DMs that come with it.",
    highlights: [
      {
        title: "Different side of the conversation",
        body:
          "CupidBot's user is the one swiping. Telepipe's user is the creator being messaged — often by hundreds of people at once.",
      },
      {
        title: "Different platform",
        body:
          "Telepipe works on Telegram, Fanvue and Instagram. It does not swipe on dating apps and does not connect to them.",
      },
      {
        title: "Different outcome",
        body:
          "The point here is not a date. It is a conversation that stays consistent for days and ends up with the fan on the creator's own page.",
      },
    ],
    sections: [
      {
        title: "If you are here to automate your own dating, this is not it",
        paragraphs: [
          "Telepipe has no dating-app integration and no swiping. If that is what you came for, nothing on this page will help and it is fairer to say so than to sell you something else.",
          "If you run a creator account — your own or someone else's — the rest of this page is the part that matters.",
        ],
      },
      {
        title: "What Telepipe actually does",
        paragraphs: [
          "It runs a model's Telegram account through Telegram's own client and answers the people who write to her, in her voice, on her schedule. When the conversation earns it, it sends her link, once, and then measures whether anyone opened it.",
          "The same persona also answers on Fanvue, where the fan has already paid, and can be pointed at Instagram, where paid links are never mentioned.",
        ],
        points: [
          "Telegram DMs from her own account",
          "Fanvue DMs through the official API",
          "One persona across all of them",
        ],
      },
    ],
    faq: [
      {
        q: "Can Telepipe swipe on Tinder or Bumble?",
        a: "No. Telepipe has no dating-app integration at all. It works on Telegram, Fanvue and Instagram.",
      },
      {
        q: "Then why does this page exist?",
        a: "Because the two products get searched together and it saves everyone time to say plainly which is which.",
      },
      {
        q: "I run a creator account — where do I start?",
        a: "With a model, her Telegram account and a persona. She can be answering the same day; the link and the funnel come once the conversation is worth it.",
      },
    ],
  },
];

export const ALTERNATIVE_SLUGS = ALTERNATIVES.map((item) => item.slug);

export function findAlternative(slug: string): Alternative | undefined {
  return ALTERNATIVES.find((item) => item.slug === slug);
}

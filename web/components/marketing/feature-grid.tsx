import Link from "next/link";
import {
  ArrowUpRight,
  AudioLines,
  BrainCircuit,
  Gauge,
  Send,
  ShoppingBag,
  Waves,
  type LucideIcon,
} from "lucide-react";

type Feature = {
  icon: LucideIcon;
  number: string;
  title: string;
  description: string;
  meta: string;
  href: string;
  signal: string;
};

const FEATURES: Feature[] = [
  {
    icon: BrainCircuit,
    number: "01",
    title: "A persona that remembers",
    description:
      "Define her backstory, tone, slang and boundaries once. Telepipe remembers every fan, every promise and every detail without breaking character.",
    meta: "Persona · long-term memory · boundaries",
    href: "/ai-model-chatbot",
    signal: "MEMORY ACTIVE",
  },
  {
    icon: Waves,
    number: "02",
    title: "She types like a person",
    description:
      "Believable pauses, split messages, natural shorthand and daily activity waves make every reply feel human — never instant or robotic.",
    meta: "Typing rhythm · activity waves · tapering",
    href: "/ai-chatter",
    signal: "HUMAN RHYTHM",
  },
  {
    icon: AudioLines,
    number: "03",
    title: "Voice notes that pass",
    description:
      "Send real ElevenLabs voice messages in her cloned voice, with the tempo and background ambience you choose for each moment.",
    meta: "Cloned voice · ambience · tempo",
    href: "/telegram-ai-chatbot",
    signal: "VOICE READY",
  },
  {
    icon: Send,
    number: "04",
    title: "Telegram, from her own account",
    description:
      "Telepipe replies from her real Telegram profile — not a bot badge — while a private control bot lets you watch or take over at any time.",
    meta: "Userbot session · control bot · takeover",
    href: "/telegram-automation",
    signal: "ACCOUNT LIVE",
  },
  {
    icon: ShoppingBag,
    number: "05",
    title: "Fanvue agent and vault selling",
    description:
      "Connect Fanvue once. She works the inbox, understands your vault folders and knows exactly which paid content to offer and when.",
    meta: "Fanvue DMs · vault folders · priced media",
    href: "/fanvue-ai-chatbot",
    signal: "VAULT CONNECTED",
  },
  {
    icon: Gauge,
    number: "06",
    title: "You see every coin she spends",
    description:
      "Every reply, summary, transcription and voice second is metered live, with daily spend per model and an automatic pause before balance runs out.",
    meta: "Usage events · daily spend · auto-pause",
    href: "/pricing",
    signal: "USAGE METERED",
  },
];

function FeatureVisual({
  icon: Icon,
  number,
  signal,
}: Pick<Feature, "icon" | "number" | "signal">) {
  return (
    <div className="relative min-h-44 overflow-hidden border-b border-white/[0.07] bg-[#0b0b0b] sm:min-h-full sm:w-[42%] sm:shrink-0 sm:border-b-0 sm:border-r">
      <div
        aria-hidden
        className="absolute inset-0 opacity-55 [background-image:linear-gradient(rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px)] [background-size:28px_28px]"
      />
      <div
        aria-hidden
        className="absolute left-1/2 top-1/2 h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.06] transition-transform duration-500 ease-out group-hover:scale-110"
      />
      <div
        aria-hidden
        className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.08] bg-white/[0.015] shadow-[0_0_50px_rgba(255,255,255,0.04)] transition-transform duration-500 ease-out group-hover:scale-105"
      />

      <div className="absolute inset-0 flex items-center justify-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/[0.12] bg-[#121212] text-white/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_18px_40px_rgba(0,0,0,0.5)] transition duration-300 group-hover:-translate-y-1 group-hover:border-white/20 group-hover:text-white">
          <Icon className="h-6 w-6" strokeWidth={1.45} />
        </span>
      </div>

      <span className="absolute left-4 top-4 font-mono text-[10px] tracking-[0.18em] text-white/25">
        {number}
      </span>
      <span className="absolute bottom-4 left-4 flex items-center gap-2 font-mono text-[9px] tracking-[0.14em] text-white/30">
        <span className="h-1.5 w-1.5 rounded-full bg-white/45 shadow-[0_0_8px_rgba(255,255,255,0.35)]" />
        {signal}
      </span>
    </div>
  );
}

function FeatureCard({ feature }: { feature: Feature }) {
  const { icon, number, title, description, meta, href, signal } = feature;

  return (
    <Link
      href={href}
      aria-label={`${title} — learn more`}
      className="group flex min-h-[310px] flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0e0e0e] outline-none transition-[transform,border-color,background-color,box-shadow] duration-300 ease-out hover:-translate-y-1 hover:border-white/[0.16] hover:bg-[#101010] hover:shadow-[0_22px_55px_rgba(0,0,0,0.42)] focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-4 focus-visible:ring-offset-black sm:min-h-[284px] sm:flex-row"
    >
      <FeatureVisual icon={icon} number={number} signal={signal} />

      <div className="flex min-w-0 flex-1 flex-col p-6 sm:p-7">
        <h2 className="max-w-sm text-[18px] font-semibold leading-snug tracking-[-0.02em] text-white sm:text-[19px]">
          {title}
        </h2>
        <p className="mt-3 text-[14px] leading-6 text-white/48">
          {description}
        </p>

        <div className="mt-auto pt-7">
          <p className="text-[9px] font-medium uppercase leading-4 tracking-[0.15em] text-white/25">
            {meta}
          </p>
          <div className="mt-4 flex items-center justify-between border-t border-white/[0.07] pt-4">
            <span className="text-[12px] font-medium text-white/45 transition-colors duration-300 group-hover:text-white/70">
              Explore feature
            </span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full border border-white/[0.09] text-white/45 transition duration-300 group-hover:border-white/20 group-hover:bg-white group-hover:text-black">
              <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={1.7} />
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}

export function FeatureGrid() {
  return (
    <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-2">
      {FEATURES.map((feature) => (
        <FeatureCard key={feature.title} feature={feature} />
      ))}
    </div>
  );
}

import type { ComponentType } from "react";

type SceneProps = { className?: string };

type Feature = {
  number: string;
  eyebrow: string;
  title: string;
  description: string;
  points: [string, string, string];
  scene: ComponentType<SceneProps>;
};

const sceneClass =
  "relative h-[290px] overflow-hidden rounded-2xl border border-white/[0.08] bg-[#090909] shadow-[inset_0_1px_0_rgba(255,255,255,0.035),0_24px_70px_rgba(0,0,0,0.35)] sm:h-[330px]";

function MemoryScene({ className = "" }: SceneProps) {
  return (
    <div className={`${sceneClass} ${className}`}>
      <div className="flex h-12 items-center justify-between border-b border-white/[0.07] px-5">
        <span className="font-mono text-[9px] tracking-[0.18em] text-white/34">
          FAN MEMORY / MAYA
        </span>
        <span className="flex items-center gap-2 text-[10px] text-white/38">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/80" />
          Synced now
        </span>
      </div>

      <div className="relative mx-auto mt-7 w-[82%]">
        <div className="absolute left-6 right-6 top-4 h-32 rounded-xl border border-white/[0.05] bg-white/[0.018]" />
        <div className="absolute left-3 right-3 top-2 h-32 rounded-xl border border-white/[0.06] bg-[#0d0d0d]" />
        <div className="relative rounded-xl border border-white/[0.1] bg-[#111111] p-5 shadow-2xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-medium text-white/86">Maya R.</p>
              <p className="mt-1 text-[9px] text-white/33">Returning fan · 47 conversations</p>
            </div>
            <span className="rounded-full border border-white/[0.08] px-2 py-1 font-mono text-[8px] tracking-[0.1em] text-white/38">
              HIGH INTENT
            </span>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-white/[0.035] px-3 py-2.5">
              <p className="text-[8px] uppercase tracking-[0.14em] text-white/25">Prefers</p>
              <p className="mt-1 text-[10px] text-white/58">Voice notes</p>
            </div>
            <div className="rounded-lg bg-white/[0.035] px-3 py-2.5">
              <p className="text-[8px] uppercase tracking-[0.14em] text-white/25">Last topic</p>
              <p className="mt-1 text-[10px] text-white/58">Weekend trip</p>
            </div>
          </div>
        </div>
        <div className="relative mx-5 -mt-1 rounded-b-xl border border-t-0 border-white/[0.08] bg-[#0c0c0c] px-4 py-3">
          <p className="text-[9px] text-white/30">PROMISE TO REMEMBER</p>
          <p className="mt-1.5 text-[10px] text-white/58">Send the new set on Friday evening.</p>
        </div>
      </div>
    </div>
  );
}

function TypingScene({ className = "" }: SceneProps) {
  return (
    <div className={`${sceneClass} ${className}`}>
      <div className="flex h-12 items-center justify-between border-b border-white/[0.07] px-5">
        <span className="font-mono text-[9px] tracking-[0.18em] text-white/34">
          LIVE CONVERSATION
        </span>
        <span className="text-[9px] text-white/30">Natural pace · 02:14</span>
      </div>
      <div className="mx-auto flex h-[calc(100%-3rem)] w-[84%] flex-col justify-center gap-3 py-6">
        <div className="max-w-[72%] self-start rounded-2xl rounded-bl-md bg-white/[0.055] px-4 py-3 text-[11px] leading-relaxed text-white/56">
          hey gorgeous, you still awake?
        </div>
        <div className="max-w-[76%] self-end rounded-2xl rounded-br-md bg-white text-black shadow-[0_10px_35px_rgba(255,255,255,0.08)]">
          <p className="px-4 py-3 text-[11px] leading-relaxed">always for you… what are you doing up this late?</p>
          <div className="border-t border-black/10 px-4 py-2 font-mono text-[8px] text-black/42">SENT AFTER 18.4 SEC</div>
        </div>
        <div className="flex items-center gap-2 self-end rounded-2xl rounded-br-md bg-white/[0.09] px-4 py-3">
          <span className="h-1.5 w-1.5 rounded-full bg-white/45" />
          <span className="h-1.5 w-1.5 rounded-full bg-white/30" />
          <span className="h-1.5 w-1.5 rounded-full bg-white/18" />
        </div>
        <p className="self-end font-mono text-[8px] tracking-[0.12em] text-white/22">
          TYPING WINDOW · 3–7 SEC
        </p>
      </div>
    </div>
  );
}

const WAVEFORM = [18, 32, 46, 64, 38, 76, 54, 28, 44, 70, 36, 58, 80, 50, 24, 42, 62, 34, 20];

function VoiceScene({ className = "" }: SceneProps) {
  return (
    <div className={`${sceneClass} ${className}`}>
      <div className="flex h-12 items-center justify-between border-b border-white/[0.07] px-5">
        <span className="font-mono text-[9px] tracking-[0.18em] text-white/34">
          VOICE STUDIO
        </span>
        <span className="rounded-full border border-white/[0.08] px-2.5 py-1 text-[8px] tracking-[0.12em] text-white/34">
          LENA V2
        </span>
      </div>
      <div className="mx-auto flex h-[calc(100%-3rem)] w-[84%] flex-col justify-center">
        <div className="rounded-2xl border border-white/[0.1] bg-[#111111] p-5 shadow-2xl">
          <div className="flex items-center gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white text-black">
              <span className="ml-0.5 h-0 w-0 border-y-[5px] border-l-[8px] border-y-transparent border-l-black" />
            </span>
            <div className="flex h-14 flex-1 items-center justify-between gap-[3px] overflow-hidden">
              {WAVEFORM.map((height, index) => (
                <span
                  key={`${height}-${index}`}
                  className="w-[3px] shrink-0 rounded-full bg-white/55"
                  style={{ height: `${height}%` }}
                />
              ))}
            </div>
            <span className="font-mono text-[9px] text-white/34">0:12</span>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-white/[0.07] px-4 py-3">
            <p className="text-[8px] uppercase tracking-[0.14em] text-white/24">Ambience</p>
            <p className="mt-1.5 text-[10px] text-white/58">Bedroom · 18%</p>
          </div>
          <div className="rounded-xl border border-white/[0.07] px-4 py-3">
            <p className="text-[8px] uppercase tracking-[0.14em] text-white/24">Delivery</p>
            <p className="mt-1.5 text-[10px] text-white/58">Warm · unhurried</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function TelegramScene({ className = "" }: SceneProps) {
  return (
    <div className={`${sceneClass} ${className}`}>
      <div className="mx-auto mt-6 w-[82%] overflow-hidden rounded-2xl border border-white/[0.09] bg-[#101010] shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3.5">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-[11px] font-semibold text-black">L</span>
            <div>
              <p className="text-[10px] font-medium text-white/82">Lena</p>
              <p className="mt-0.5 text-[8px] text-emerald-400/75">online · replying</p>
            </div>
          </div>
          <span className="rounded-full border border-white/[0.08] px-2.5 py-1 font-mono text-[8px] tracking-[0.12em] text-white/34">
            REAL ACCOUNT
          </span>
        </div>
        <div className="space-y-3 p-4">
          <div className="w-[68%] rounded-xl rounded-bl-sm bg-white/[0.055] px-3.5 py-2.5 text-[10px] text-white/52">
            omg your voice… where can I see more?
          </div>
          <div className="ml-auto w-[74%] rounded-xl rounded-br-sm bg-white px-3.5 py-2.5 text-[10px] text-black/78">
            everything is here, baby — want the private set?
          </div>
        </div>
      </div>
      <div className="mx-auto mt-3 flex w-[82%] items-center justify-between rounded-xl border border-white/[0.07] px-4 py-3">
        <div>
          <p className="text-[8px] uppercase tracking-[0.14em] text-white/24">Private control bot</p>
          <p className="mt-1 text-[9px] text-white/48">Watching this conversation</p>
        </div>
        <span className="h-5 w-9 rounded-full bg-white p-0.5">
          <span className="block h-4 w-4 translate-x-4 rounded-full bg-black" />
        </span>
      </div>
    </div>
  );
}

const VAULT_ITEMS = [
  { label: "SET 04", price: "$19", tone: "from-[#242424] to-[#111111]" },
  { label: "VIDEO 02", price: "$29", tone: "from-[#303030] to-[#151515]" },
  { label: "PRIVATE", price: "$49", tone: "from-[#1f1f1f] to-[#0d0d0d]" },
];

function VaultScene({ className = "" }: SceneProps) {
  return (
    <div className={`${sceneClass} ${className}`}>
      <div className="flex h-12 items-center justify-between border-b border-white/[0.07] px-5">
        <span className="font-mono text-[9px] tracking-[0.18em] text-white/34">FANVUE VAULT</span>
        <span className="text-[9px] text-white/30">24 items connected</span>
      </div>
      <div className="mx-auto w-[86%] py-7">
        <div className="grid grid-cols-3 gap-3">
          {VAULT_ITEMS.map((item, index) => (
            <div key={item.label} className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#0d0d0d]">
              <div className={`relative h-24 bg-gradient-to-br ${item.tone}`}>
                <span className="absolute left-3 top-3 font-mono text-[8px] tracking-[0.14em] text-white/30">0{index + 1}</span>
                <span className="absolute inset-x-3 bottom-3 h-px bg-white/[0.08]" />
              </div>
              <div className="flex items-center justify-between px-3 py-3">
                <span className="text-[8px] tracking-[0.12em] text-white/30">{item.label}</span>
                <span className="text-[10px] font-medium text-white/70">{item.price}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-center justify-between rounded-xl border border-white/[0.07] px-4 py-3">
          <div>
            <p className="text-[8px] uppercase tracking-[0.14em] text-white/24">Active sales rule</p>
            <p className="mt-1 text-[9px] text-white/50">Offer after trust is established</p>
          </div>
          <span className="font-mono text-[8px] tracking-[0.12em] text-white/34">8+ MSG</span>
        </div>
      </div>
    </div>
  );
}

const SPEND_BARS = [24, 42, 31, 58, 47, 76, 64, 88, 55, 70, 48, 82];

function UsageScene({ className = "" }: SceneProps) {
  return (
    <div className={`${sceneClass} ${className}`}>
      <div className="flex h-12 items-center justify-between border-b border-white/[0.07] px-5">
        <span className="font-mono text-[9px] tracking-[0.18em] text-white/34">LIVE USAGE</span>
        <span className="flex items-center gap-2 text-[9px] text-white/34">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/80" />
          Metering
        </span>
      </div>
      <div className="mx-auto w-[84%] py-7">
        <div className="flex items-end justify-between">
          <div>
            <p className="text-[9px] uppercase tracking-[0.15em] text-white/24">Spent today</p>
            <p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-white">$3.84</p>
          </div>
          <p className="font-mono text-[8px] tracking-[0.12em] text-white/28">1,248 EVENTS</p>
        </div>
        <div className="mt-6 flex h-20 items-end gap-2 border-b border-white/[0.08] pb-px">
          {SPEND_BARS.map((height, index) => (
            <span
              key={`${height}-${index}`}
              className="flex-1 rounded-t-sm bg-white/[0.12] last:bg-white/70"
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
        <div className="mt-5 grid grid-cols-3 divide-x divide-white/[0.07] rounded-xl border border-white/[0.07] py-3">
          <div className="px-3">
            <p className="text-[8px] text-white/24">Replies</p>
            <p className="mt-1 text-[10px] text-white/58">$2.41</p>
          </div>
          <div className="px-3">
            <p className="text-[8px] text-white/24">Voice</p>
            <p className="mt-1 text-[10px] text-white/58">$0.96</p>
          </div>
          <div className="px-3">
            <p className="text-[8px] text-white/24">Memory</p>
            <p className="mt-1 text-[10px] text-white/58">$0.47</p>
          </div>
        </div>
      </div>
    </div>
  );
}

const FEATURES: Feature[] = [
  {
    number: "01",
    eyebrow: "Persona & memory",
    title: "A persona that remembers",
    description:
      "Define her backstory, tone and boundaries once. Telepipe remembers every fan, every promise and the details that make the next message feel personal.",
    points: ["Long-term fan memory", "Consistent voice and slang", "Hard boundaries that hold"],
    scene: MemoryScene,
  },
  {
    number: "02",
    eyebrow: "Human timing",
    title: "She types like a person",
    description:
      "Replies arrive with believable pauses, natural message splits and a daily rhythm — never instantly, never with the same robotic cadence.",
    points: ["Believable response delay", "Natural message splitting", "Daily activity waves"],
    scene: TypingScene,
  },
  {
    number: "03",
    eyebrow: "Cloned voice",
    title: "Voice notes that pass",
    description:
      "Send ElevenLabs voice notes in her cloned voice, with the right tempo and just enough background ambience to match where she says she is.",
    points: ["ElevenLabs voice clone", "Adjustable ambience", "Frequency and tempo control"],
    scene: VoiceScene,
  },
  {
    number: "04",
    eyebrow: "Telegram agent",
    title: "From her real account",
    description:
      "Telepipe works from her genuine Telegram profile instead of a bot account. A private control bot lets you watch and take over whenever you want.",
    points: ["Real Telegram profile", "Private control bot", "Instant human takeover"],
    scene: TelegramScene,
  },
  {
    number: "05",
    eyebrow: "Fanvue sales",
    title: "An agent that knows the vault",
    description:
      "Connect Fanvue once. She understands what is inside each vault folder, what it costs and when the conversation is ready for an offer.",
    points: ["Fanvue inbox automation", "Vault-aware selling", "Price rules per folder"],
    scene: VaultScene,
  },
  {
    number: "06",
    eyebrow: "Transparent usage",
    title: "See every coin she spends",
    description:
      "Every reply, summary, transcription and voice second is metered live, with spend per model and automatic protection before the balance runs out.",
    points: ["Live usage events", "Daily spend per model", "Automatic balance protection"],
    scene: UsageScene,
  },
];

function FeatureRow({ feature, index }: { feature: Feature; index: number }) {
  const Scene = feature.scene;
  const reversed = index % 2 === 1;

  return (
    <article className="grid gap-8 border-t border-white/[0.075] py-10 first:border-t-0 sm:py-14 lg:grid-cols-12 lg:items-center lg:gap-14">
      <div className={`lg:col-span-7 ${reversed ? "lg:order-2" : ""}`}>
        <Scene />
      </div>
      <div className={`lg:col-span-5 ${reversed ? "lg:order-1" : ""}`}>
        <div className="flex items-center gap-3 font-mono text-[9px] uppercase tracking-[0.18em] text-white/30">
          <span>{feature.number}</span>
          <span className="h-px w-6 bg-white/[0.12]" />
          <span>{feature.eyebrow}</span>
        </div>
        <h2 className="mt-5 max-w-md text-2xl font-semibold leading-tight tracking-[-0.035em] text-white sm:text-[30px]">
          {feature.title}
        </h2>
        <p className="mt-4 max-w-md text-[15px] leading-7 text-white/46">
          {feature.description}
        </p>
        <ul className="mt-7 space-y-3 border-t border-white/[0.07] pt-6">
          {feature.points.map((point) => (
            <li key={point} className="flex items-center gap-3 text-[12px] text-white/48">
              <span className="h-1 w-1 rounded-full bg-white/45" />
              {point}
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

export function FeatureGrid() {
  return (
    <div className="mx-auto max-w-6xl">
      {FEATURES.map((feature, index) => (
        <FeatureRow key={feature.title} feature={feature} index={index} />
      ))}
    </div>
  );
}

"use client";

import { useEffect, useRef, useState, type ComponentType } from "react";
import dynamic from "next/dynamic";
import {
  AudioLines,
  BrainCircuit,
  Gauge,
  Send,
  ShoppingBag,
  Waves,
  type LucideIcon,
} from "lucide-react";

/**
 * Karta funkcie s animovaným shaderom za tmavým panelom.
 *
 * Výkon (WebGL kontext na kartu nie je zadarmo):
 *  1. `next/dynamic` bez SSR — `@paper-design/shaders-react` (~30 kB gz) sa
 *     nedostane do initial bundlu ani do serverového renderu.
 *  2. IntersectionObserver — canvas sa vytvorí až keď je karta 240 px pred
 *     viewportom. Nad záhybom sa tak štartujú 1–2 kontexty, nie šesť.
 *     Po prvom zobrazení ostáva pripojený (znovuvytváranie WebGL kontextu je
 *     drahšie než ho nechať bežať).
 *  3. `maxPixelCount` strop + `minPixelRatio={1}` — na retine sa nerenderuje
 *     4× viac pixelov, než karta reálne potrebuje.
 *  4. `prefers-reduced-motion` **a coarse pointer / úzky viewport** dostanú
 *     statický gradient z tej istej palety — na mobile teda nebeží WebGL vôbec.
 */
const Warp = dynamic(
  () => import("@paper-design/shaders-react").then((mod) => mod.Warp),
  { ssr: false },
) as ComponentType<Record<string, unknown>>;

type ShaderPreset = {
  colors: string[];
  shape: "checks" | "stripes" | "edge";
  proportion: number;
  softness: number;
  distortion: number;
  swirl: number;
  swirlIterations: number;
  shapeScale: number;
  scale: number;
  rotation: number;
  speed: number;
  /** Statická náhrada — tie isté odtiene, žiadny canvas. */
  fallback: string;
};

/**
 * Shader presety — monochróm.
 *
 * Predloha mala farebné HSL palety; tu je každá zložená len z odtieňov čiernej
 * a bielej. Karty sa preto nelíšia farbou, ale pohybom: iný `shape`,
 * `proportion`, `softness`, `distortion` a `swirl`. `fallback` je ten istý
 * odtieň staticky (mobil + prefers-reduced-motion).
 */
const PRESETS: ShaderPreset[] = [
  {
    colors: ["#050505", "#2f2f2f", "#8f8f8f", "#f4f4f5"],
    shape: "stripes",
    proportion: 0.34,
    softness: 0.92,
    distortion: 0.16,
    swirl: 0.62,
    swirlIterations: 9,
    shapeScale: 0.18,
    scale: 1.05,
    rotation: 24,
    speed: 0.32,
    fallback:
      "radial-gradient(130% 100% at 20% 0%, rgba(255,255,255,0.24) 0%, rgba(255,255,255,0.05) 42%, transparent 72%), linear-gradient(150deg, #2a2a2a 0%, #0b0b0b 70%)",
  },
  {
    colors: ["#0a0a0a", "#1c1c1c", "#6b6b6b", "#d9d9de"],
    shape: "checks",
    proportion: 0.5,
    softness: 0.42,
    distortion: 0.38,
    swirl: 0.18,
    swirlIterations: 4,
    shapeScale: 0.3,
    scale: 0.85,
    rotation: 0,
    speed: 0.24,
    fallback:
      "radial-gradient(120% 110% at 80% 10%, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.04) 46%, transparent 74%), linear-gradient(200deg, #1f1f1f 0%, #070707 68%)",
  },
  {
    colors: ["#000000", "#4a4a4a", "#a5a5a5", "#ffffff"],
    shape: "edge",
    proportion: 0.62,
    softness: 1,
    distortion: 0.08,
    swirl: 0.85,
    swirlIterations: 14,
    shapeScale: 0.12,
    scale: 1.3,
    rotation: 118,
    speed: 0.18,
    fallback:
      "radial-gradient(100% 120% at 50% 100%, rgba(255,255,255,0.26) 0%, rgba(255,255,255,0.05) 40%, transparent 70%), linear-gradient(20deg, #262626 0%, #050505 72%)",
  },
  {
    colors: ["#111111", "#282828", "#7d7d7d", "#e9e9ec"],
    shape: "stripes",
    proportion: 0.72,
    softness: 0.2,
    distortion: 0.44,
    swirl: 0.3,
    swirlIterations: 6,
    shapeScale: 0.42,
    scale: 0.72,
    rotation: 72,
    speed: 0.4,
    fallback:
      "repeating-linear-gradient(115deg, rgba(255,255,255,0.09) 0px, rgba(255,255,255,0.09) 2px, transparent 2px, transparent 16px), linear-gradient(160deg, #232323 0%, #080808 74%)",
  },
  {
    colors: ["#070707", "#3c3c3c", "#b4b4b4", "#fafafa"],
    shape: "checks",
    proportion: 0.28,
    softness: 0.78,
    distortion: 0.26,
    swirl: 0.48,
    swirlIterations: 11,
    shapeScale: 0.2,
    scale: 1.15,
    rotation: 200,
    speed: 0.22,
    fallback:
      "radial-gradient(140% 90% at 0% 60%, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.04) 44%, transparent 76%), linear-gradient(130deg, #1c1c1c 0%, #060606 70%)",
  },
  {
    colors: ["#0d0d0d", "#212121", "#727272", "#c7c7cc"],
    shape: "edge",
    proportion: 0.46,
    softness: 0.58,
    distortion: 0.62,
    swirl: 0.1,
    swirlIterations: 3,
    shapeScale: 0.26,
    scale: 0.95,
    rotation: 300,
    speed: 0.34,
    fallback:
      "radial-gradient(110% 130% at 100% 100%, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.03) 48%, transparent 78%), linear-gradient(240deg, #1e1e1e 0%, #050505 66%)",
  },
];

/**
 * Šesť najsilnejších reálnych schopností — všetko existuje v produkte:
 * persona/memory/facts/recall, humanize + den (aktivitné vlny), eleven/voices
 * (hlasovky s ambience), Telegram userbot cez Telethon, Fanvue agent + vault
 * s cenami médií, `usage_events` s účtovaním za každé AI volanie.
 */
const FEATURES = [
  {
    icon: BrainCircuit,
    title: "A persona that remembers",
    body: "Backstory, tone, slang and hard boundaries — defined once. From there she keeps notes on every fan: their name, their job, what they asked for last week, the promise she made on Tuesday. Thousands of parallel chats, never a broken character.",
    meta: "Persona · long-term memory · boundaries",
  },
  {
    icon: Waves,
    title: "She types like a person",
    body: "Replies arrive after a believable pause, split across a couple of messages, with her own typos and shorthand. Activity waves give her a day: chatty in the evening, slow in the morning, occasionally busy — because nobody answers in 400 ms at 4am.",
    meta: "Typing rhythm · activity waves · tapering",
  },
  {
    icon: AudioLines,
    title: "Voice notes that pass",
    body: "Real ElevenLabs voice messages in her own cloned voice, with tempo and background ambience — bedroom, street, café — mixed at the level you set. You choose how often she sends one instead of typing.",
    meta: "Cloned voice · ambience · tempo",
  },
  {
    icon: Send,
    title: "Telegram, from her own account",
    body: "Not a bot account with a bot badge. Telepipe signs in with her phone number and replies from the real profile, while a private control bot keeps you in the loop and lets you take over mid-chat.",
    meta: "Userbot session · control bot · takeover",
  },
  {
    icon: ShoppingBag,
    title: "Fanvue agent and vault selling",
    body: "Connect Fanvue once and she works that inbox too. Her media stays in your Fanvue vault — here you just say what each folder is for and what it costs, so paid content never leaves for free.",
    meta: "Fanvue DMs · vault folders · priced media",
  },
  {
    icon: Gauge,
    title: "You see every cent she spends",
    body: "Each AI call — reply, summary, image read, transcription, voice second — is metered as it happens and charged against your credit balance. Daily spend per model, breakdown by kind, and an automatic pause before the balance ever goes negative.",
    meta: "Usage events · daily spend · auto-pause",
  },
];

/** Karta smie renderovať shader? (mount-safe, bez hydration mismatchu) */
function useShaderAllowed() {
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const queries = [
      window.matchMedia("(prefers-reduced-motion: reduce)"),
      // Mobil/tablet a dotykové zariadenia — šesť WebGL kontextov by tam bola
      // zbytočná daň za dekoráciu.
      window.matchMedia("(max-width: 767px)"),
      window.matchMedia("(pointer: coarse)"),
    ];
    const evaluate = () => setAllowed(!queries.some((q) => q.matches));
    evaluate();
    queries.forEach((q) => q.addEventListener("change", evaluate));
    return () => queries.forEach((q) => q.removeEventListener("change", evaluate));
  }, []);

  return allowed;
}

/** Namountuj až keď je prvok blízko viewportu; potom to už nevracaj späť. */
function useNearViewport<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || near) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: "240px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [near]);

  return [ref, near] as const;
}

function ShaderCard({
  index,
  icon: Icon,
  title,
  body,
  meta,
  preset,
}: {
  index: number;
  icon: LucideIcon;
  title: string;
  body: string;
  meta: string;
  preset: ShaderPreset;
}) {
  const allowed = useShaderAllowed();
  const [ref, near] = useNearViewport<HTMLElement>();
  const live = allowed && near;

  return (
    <article
      ref={ref}
      className="lp-shader-card group relative isolate overflow-hidden rounded-[22px] p-2.5"
    >
      {/* Vrstva 1 — shader alebo jeho statická náhrada */}
      <div aria-hidden className="absolute inset-0 -z-10">
        <div
          className="absolute inset-0"
          style={{ backgroundImage: preset.fallback }}
        />
        {live && (
          <Warp
            className="absolute inset-0 h-full w-full"
            colors={preset.colors}
            shape={preset.shape}
            proportion={preset.proportion}
            softness={preset.softness}
            distortion={preset.distortion}
            swirl={preset.swirl}
            swirlIterations={preset.swirlIterations}
            shapeScale={preset.shapeScale}
            scale={preset.scale}
            rotation={preset.rotation}
            speed={preset.speed}
            minPixelRatio={1}
            maxPixelCount={480 * 480}
          />
        )}
        {/* Stmavenie, aby text mal vždy kontrast bez ohľadu na fázu shaderu */}
        <div className="absolute inset-0 bg-black/45" />
      </div>

      {/* Vrstva 2 — tmavý priesvitný panel s obsahom */}
      <div className="lp-shader-panel relative flex h-full flex-col rounded-[15px] p-6 sm:p-7">
        <div className="flex items-start justify-between gap-4">
          <span className="lp-icon-chip h-10 w-10 shrink-0 transition-colors duration-300 group-hover:border-white/20 group-hover:text-white">
            <Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </span>
          <span className="font-mono text-[10px] text-white/25">
            {String(index + 1).padStart(2, "0")}
          </span>
        </div>

        <h2 className="mt-6 text-[17px] font-semibold text-white">{title}</h2>
        <p className="mt-2.5 text-[14px] leading-relaxed text-white/50">{body}</p>
        <p className="mt-auto pt-6 text-[11px] font-medium uppercase tracking-[0.14em] text-white/25">
          {meta}
        </p>
      </div>
    </article>
  );
}

export function FeatureGrid() {
  return (
    <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-2 xl:grid-cols-3">
      {FEATURES.map((feature, index) => (
        <ShaderCard
          key={feature.title}
          index={index}
          icon={feature.icon}
          title={feature.title}
          body={feature.body}
          meta={feature.meta}
          preset={PRESETS[index]}
        />
      ))}
    </div>
  );
}

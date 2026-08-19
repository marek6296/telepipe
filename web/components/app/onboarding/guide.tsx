"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  Coins,
  Info,
  Smartphone,
  Sparkles,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { markOnboardingDoneAction } from "@/app/app/actions";
import { cn } from "@/lib/utils";

/**
 * Uvítanie po odomknutí účtu — a tá istá pomôcka kedykoľvek neskôr.
 *
 * JEDEN OBSAH, DVA VCHODY. `WelcomeDialog` sa otvorí sám raz po schválení a
 * zavretie si zapíše do databázy. `HelpGuideButton` otvorí to isté na
 * požiadanie a nezapisuje nič. Keby to boli dva texty, jeden by časom zostarol
 * a človek by dostal dve rôzne odpovede na tú istú otázku.
 *
 * KROKY SEDIA NA SKUTOČNÝ SPRIEVODCU (`components/app/telegram/wizard.tsx`):
 * API kľúče → telefón → kód → kontrolný bot (voliteľný) → zapnutie. Návod,
 * ktorý sľúbi iné poradie, je horší než žiadny — človek podľa neho hľadá
 * tlačidlo, ktoré neexistuje.
 */

/* -------------------------------------------------------------------------- */
/*  Obsah                                                                      */
/* -------------------------------------------------------------------------- */

type Step = {
  icon: LucideIcon;
  title: string;
  body: string;
  /** Voliteľné = smie sa preskočiť. Vypisuje sa to, nech to nikto nehľadá. */
  optional?: boolean;
};

const STEPS: Step[] = [
  {
    icon: Sparkles,
    title: "Create her",
    body: "Hit “Add agent” on the dashboard, pick a type and give her a name. The name you can change later, the type you cannot.",
  },
  {
    icon: Smartphone,
    title: "Sign her Telegram in",
    body: "Her own Telegram account is what talks to people, so this one is required. You need her API keys from my.telegram.org, her phone number, and the code Telegram sends. No number yet? Buy one under Virtual SIM.",
  },
  {
    icon: Bot,
    title: "Add a control bot",
    optional: true,
    body: "Create a bot with @BotFather, paste its token, then send that bot /start from your own Telegram. It reports to you and lets you run her from your phone — pause her, read chats, switch her replies off.",
  },
  {
    icon: Zap,
    title: "Give her a personality, then switch her on",
    body: "The Persona tab decides who she is and how she writes. When it reads like her, flip her on — she starts replying straight away.",
  },
];

/* -------------------------------------------------------------------------- */
/*  Obrázok — čo je vlastne na koho napojené                                   */
/* -------------------------------------------------------------------------- */

/**
 * Tri veci, ktoré si ľudia pletú najviac: JEJ účet odpovedá, TVOJ bot ťa
 * informuje, a TVOJ Telegram je miesto, kam ti ten bot píše. Text to vysvetľuje
 * v krokoch, ale kým to človek nevidí vedľa seba, myslí si, že je to jedno a to
 * isté napojenie.
 */
function Diagram() {
  const nodes = [
    { icon: Smartphone, label: "Her Telegram", note: "does the replying", tone: "#2aabee" },
    { icon: Sparkles, label: "TelePipe", note: "writes what she says", tone: "#d4af37" },
    { icon: Bot, label: "Your phone", note: "control bot reports here", tone: "#7a7a84" },
  ];

  // Mriežka s vlastným stĺpcom pre spojnicu. Predtým to bol flex so zápornou
  // horným odsadením a spojnice sa podľa dĺžky popisiek stratili — takto sedí
  // čiara vždy v strede ikony (h-9 = 36 px, teda 17 px zhora) bez ohľadu na to,
  // na koľko riadkov sa text zalomí.
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] p-4">
      <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-start">
        {nodes.map((node, index) => {
          const Icon = node.icon;
          return (
            <Fragment key={node.label}>
              <div className="px-1 text-center">
                <span
                  className="mx-auto flex h-9 w-9 items-center justify-center rounded-lg border"
                  style={{ borderColor: `${node.tone}55`, background: `${node.tone}14` }}
                >
                  <Icon className="h-4 w-4" strokeWidth={1.75} style={{ color: node.tone }} />
                </span>
                <span className="mt-2 block text-[11.5px] leading-tight font-medium text-[var(--app-text-2)]">
                  {node.label}
                </span>
                <span className="mt-1 block text-[10.5px] leading-tight text-[var(--app-text-4)]">
                  {node.note}
                </span>
              </div>
              {index < nodes.length - 1 && (
                <span
                  aria-hidden
                  className="mt-[17px] h-px w-4 self-start bg-[var(--app-border-strong)] sm:w-7"
                />
              )}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Telo návodu                                                                */
/* -------------------------------------------------------------------------- */

function GuideBody({ startCoins, onDone }: { startCoins: number; onDone: () => void }) {
  return (
    <>
      <div className="flex items-center gap-2.5">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style={{ background: "rgba(212, 175, 55, 0.14)", border: "1px solid rgba(212, 175, 55, 0.35)" }}
        >
          <Sparkles className="h-4 w-4" strokeWidth={1.75} style={{ color: "var(--gold)" }} />
        </span>
        <div className="min-w-0">
          <h2 className="text-[16px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
            You&rsquo;re in
          </h2>
          <p className="text-[12.5px] text-[var(--app-text-4)]">
            Four steps and she&rsquo;s answering people.
          </p>
        </div>
      </div>

      {startCoins > 0 && (
        <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-[var(--app-border)] bg-[var(--app-surface)] px-3.5 py-3">
          <Coins className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} style={{ color: "var(--gold)" }} />
          <p className="text-[12.5px] leading-relaxed text-[var(--app-text-2)]">
            <span className="text-[var(--app-text)]">
              {startCoins.toLocaleString("en-US")} Pipe Coins are already on your balance
            </span>{" "}
            — enough to build her profile and see her reply. When they run low you top up under{" "}
            <Link href="/app/billing" className="underline underline-offset-2 hover:text-[var(--app-text)]">
              Billing
            </Link>
            .
          </p>
        </div>
      )}

      <div className="mt-4">
        <Diagram />
      </div>

      <ol className="mt-4 space-y-3">
        {STEPS.map((step, index) => {
          const Icon = step.icon;
          return (
            <li key={step.title} className="flex gap-3">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[11.5px] font-semibold tabular-nums text-[var(--app-text-3)]">
                {index + 1}
              </span>
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-1.5 text-[13.5px] font-medium text-[var(--app-text)]">
                  <Icon className="h-3.5 w-3.5 shrink-0 text-[var(--app-text-4)]" strokeWidth={1.75} />
                  {step.title}
                  {step.optional && (
                    <span className="rounded-full border border-[var(--app-border)] px-1.5 py-px text-[10px] font-normal tracking-wide text-[var(--app-text-4)] uppercase">
                      optional
                    </span>
                  )}
                </p>
                <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--app-text-3)]">
                  {step.body}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      <p className="mt-4 text-[12px] leading-relaxed text-[var(--app-text-4)]">
        Stuck anywhere? The same guide is under the{" "}
        <Info className="inline h-3 w-3 align-[-1px]" strokeWidth={2} /> button on your Account
        page, and you can message us in the chat at the bottom right.
      </p>

      <button type="button" onClick={onDone} className="app-btn app-btn-primary mt-5 h-10 w-full justify-center">
        Let&rsquo;s go
      </button>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/*  Škrupina dialógu                                                           */
/* -------------------------------------------------------------------------- */

function GuideDialog({
  open,
  startCoins,
  onClose,
}: {
  open: boolean;
  startCoins: number;
  onClose: () => void;
}) {
  // Escape zatvára — bez toho je to na klávesnici pasca.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[95] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/75"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Getting started"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="app-panel relative max-h-[90vh] w-full max-w-[30rem] overflow-y-auto p-6"
          >
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="app-tap absolute top-3 right-3 rounded-md p-1.5 text-[var(--app-text-4)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
            >
              <X className="h-4 w-4" strokeWidth={1.75} />
            </button>

            <GuideBody startCoins={startCoins} onDone={onClose} />
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

/* -------------------------------------------------------------------------- */
/*  Vchod 1 — samo po odomknutí                                                */
/* -------------------------------------------------------------------------- */

/**
 * Server rozhodne, či sa okno má ukázať (`show`), klient si to zapíše späť.
 *
 * Zápis ide HNEĎ pri zavretí a jeho výsledok sa nečaká: keby server nestíhal,
 * človek by pozeral na zamrznuté okno. Najhoršie, čo sa môže stať pri zlyhaní,
 * je že sa mu návod raz ukáže znova.
 */
export function WelcomeDialog({ show, startCoins }: { show: boolean; startCoins: number }) {
  const [open, setOpen] = useState(show);

  const close = useCallback(() => {
    setOpen(false);
    void markOnboardingDoneAction();
  }, []);

  return <GuideDialog open={open} startCoins={startCoins} onClose={close} />;
}

/* -------------------------------------------------------------------------- */
/*  Vchod 2 — „i" kedykoľvek                                                   */
/* -------------------------------------------------------------------------- */

export function HelpGuideButton({
  startCoins,
  label = "How do I start?",
  className,
}: {
  startCoins: number;
  label?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn("app-btn app-btn-ghost h-9 px-3.5", className)}
      >
        <Info className="h-3.5 w-3.5" strokeWidth={1.75} />
        {label}
      </button>

      <GuideDialog open={open} startCoins={startCoins} onClose={() => setOpen(false)} />
    </>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, Loader2, RefreshCw, Sparkles } from "lucide-react";

import {
  applyPersonaDraftAction,
  generatePersonaDraftAction,
} from "@/app/app/m/[id]/persona/build/actions";
import { Callout } from "@/components/app/ui";
import type { PersonaDraft } from "@/lib/persona-draft";
import { LanguageFields } from "@/components/app/forms/language-picker";
import {
  CHAT_WINDOWS,
  EMOJI_LEVELS,
  EMPTY_ANSWERS,
  MAX_VIBES,
  PACE_LEVELS,
  MSG_LENGTHS,
  SLANG_LEVELS,
  SPICE_LEVELS,
  VIBES,
  WIZARD_MAX_AGE,
  WIZARD_MIN_AGE,
  choiceOf,
  type Choice,
  type WizardAnswers,
} from "@/lib/persona-wizard";
import { cn } from "@/lib/utils";

/**
 * Asistovaná tvorba persony — osem otázok, jedno generovanie, jedna kontrola.
 *
 * PREČO TAK MÁLO OTÁZOK: karta Persona má trinásť polí a karta Behavior ďalších
 * štyridsať. Klient, ktorý zakladá prvú modelku, nevie, čo do nich patrí — a
 * väčšina z nich sa dá odvodiť. Pýtame sa len na to, čo sa odvodiť NEDÁ (kto je,
 * kde žije, ako ďaleko smie zájsť), zvyšok napíše model.
 *
 * SPUSTIŤ SA DÁ KEDYKOĽVEK, nielen na prázdnej karte. Prestavať charakter je
 * bežná vec (iný jazyk, iné tempo, iná platforma) — preto `overwrites`: keď je
 * persona vypísaná, povie sa to na úvodnej aj na kontrolnej obrazovke, lebo
 * Apply prepíše aj to, čo si klient napísal sám.
 *
 * NIČ SA NEUKLADÁ, KÝM KLIENT NEPOVIE. Generovanie vráti draft do prehliadača,
 * zapisuje sa až „Apply" — a to cez tie isté akcie ako obyčajné karty.
 */

type Phase = "intro" | "questions" | "review";

const LAST_STEP = 7;

/** Hlášky počas generovania — bez nich je to tridsať sekúnd prázdnej obrazovky. */
const PROGRESS = [
  "Reading your answers…",
  "Working out where she lives and what her days look like…",
  "Writing her story…",
  "Teaching her how she texts…",
  "Checking everything against our settings…",
];

export function PersonaWizard({
  modelId,
  modelName,
  blockedReason,
  overwrites = false,
}: {
  modelId: string;
  modelName: string;
  /** Neprázdne = generovať sa teraz nedá (kredit, chýbajúca konfigurácia). */
  blockedReason?: string;
  /** Persona už je vypísaná — Apply ju prepíše, a to treba povedať dopredu. */
  overwrites?: boolean;
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("intro");
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<WizardAnswers>({
    ...EMPTY_ANSWERS,
    name: modelName,
  });
  const [draft, setDraft] = useState<PersonaDraft | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [generating, startGenerating] = useTransition();
  const [applying, startApplying] = useTransition();

  const set = <K extends keyof WizardAnswers>(key: K, value: WizardAnswers[K]) =>
    setAnswers((previous) => ({ ...previous, [key]: value }));

  const stepError = useMemo(() => validateStep(step, answers), [step, answers]);

  const generate = () => {
    setError("");
    startGenerating(async () => {
      const result = await generatePersonaDraftAction(modelId, answers);
      if (result.error || !result.draft) {
        setError(result.error ?? "Something went wrong.");
        return;
      }
      setDraft(result.draft);
      setWarnings(result.warnings ?? []);
      setPhase("review");
    });
  };

  const apply = () => {
    if (!draft) return;
    setError("");
    startApplying(async () => {
      const result = await applyPersonaDraftAction(modelId, draft);
      if (result.error) {
        setError(result.error);
        return;
      }
      router.push(`/app/m/${modelId}/persona`);
      router.refresh();
    });
  };

  if (generating) return <GeneratingCard />;

  if (phase === "intro") {
    return (
      <IntroCard
        modelId={modelId}
        blockedReason={blockedReason}
        overwrites={overwrites}
        onStart={() => {
          setPhase("questions");
          setStep(0);
        }}
      />
    );
  }

  if (phase === "review" && draft) {
    return (
      <ReviewCard
        draft={draft}
        overwrites={overwrites}
        warnings={warnings}
        error={error}
        applying={applying}
        onApply={apply}
        onRegenerate={generate}
        onBack={() => setPhase("questions")}
      />
    );
  }

  return (
    <div className="app-card overflow-hidden">
      <Progress step={step} />

      <div className="px-5 py-6 sm:px-7 sm:py-7">
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -12 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          >
            <StepBody step={step} answers={answers} set={set} />
          </motion.div>
        </AnimatePresence>

        {error && (
          <div className="mt-5">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}

        <div className="mt-7 flex items-center justify-between gap-3 border-t border-[var(--app-border)] pt-5">
          <button
            type="button"
            onClick={() => (step === 0 ? setPhase("intro") : setStep(step - 1))}
            className="app-btn app-btn-quiet h-9 px-3"
          >
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
            Back
          </button>

          <div className="flex items-center gap-3">
            {stepError && (
              <span className="hidden text-[11.5px] text-[var(--app-text-4)] sm:inline">
                {stepError}
              </span>
            )}
            {step < LAST_STEP ? (
              <button
                type="button"
                disabled={Boolean(stepError)}
                onClick={() => setStep(step + 1)}
                className="app-btn app-btn-primary h-9 px-4"
              >
                Continue
                <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} />
              </button>
            ) : (
              <button
                type="button"
                disabled={Boolean(stepError) || Boolean(blockedReason)}
                onClick={generate}
                className="app-btn app-btn-primary h-9 px-4"
              >
                <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} />
                Build her
              </button>
            )}
          </div>
        </div>

        {step === LAST_STEP && blockedReason && (
          <div className="mt-4">
            <Callout tone="danger">{blockedReason}</Callout>
          </div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Úvod — „nechaj to na AI" vs „vyplním si to sám"
-------------------------------------------------------------------------- */

function IntroCard({
  modelId,
  blockedReason,
  overwrites,
  onStart,
}: {
  modelId: string;
  blockedReason?: string;
  overwrites?: boolean;
  onStart: () => void;
}) {
  return (
    <div className="app-card px-6 py-10 sm:px-10 sm:py-12">
      <div className="mx-auto max-w-lg text-center">
        <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--app-border)] text-[var(--app-text-4)]">
          <Sparkles className="h-4 w-4" strokeWidth={1.5} />
        </span>
        <h2 className="mt-5 text-[17px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
          {overwrites ? "Build her again?" : "Want help building her?"}
        </h2>
        <p className="mt-2.5 text-[13px] leading-relaxed text-[var(--app-text-3)]">
          Answer eight quick questions — mostly taps — and we write her whole persona for
          you: her story, how she texts, what she never does, how she leads a chat to your
          link, and the rhythm she answers in. You can change every word afterwards on the
          normal tabs.
        </p>

        {overwrites && (
          <div className="mt-6 text-left">
            <Callout tone="gold">
              She is already set up. Nothing changes while you answer — but if you approve
              the result at the end, it replaces what is on her Persona and Behavior tabs,
              including anything you wrote yourself.
            </Callout>
          </div>
        )}

        {blockedReason ? (
          <div className="mt-6 text-left">
            <Callout tone="danger">{blockedReason}</Callout>
          </div>
        ) : (
          <button
            type="button"
            onClick={onStart}
            className="app-btn app-btn-primary mt-7 h-10 px-5"
          >
            <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} />
            Build her with AI
          </button>
        )}

        <p className="mt-5 text-[12px] text-[var(--app-text-4)]">
          Or{" "}
          <Link
            href={`/app/m/${modelId}/telegram`}
            className="underline underline-offset-2 transition-colors hover:text-[var(--app-text-2)]"
          >
            set her up manually
          </Link>{" "}
          — connect Telegram first and fill the tabs in yourself.
        </p>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Generovanie
-------------------------------------------------------------------------- */

function GeneratingCard() {
  const [index, setIndex] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    timer.current = setInterval(
      () => setIndex((value) => Math.min(value + 1, PROGRESS.length - 1)),
      6000,
    );
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  return (
    <div className="app-card px-6 py-16 text-center">
      <div className="mx-auto flex max-w-sm flex-col items-center">
        <Loader2
          className="h-5 w-5 animate-spin text-[var(--app-text-3)]"
          strokeWidth={1.75}
        />
        <p className="mt-5 text-[13.5px] text-[var(--app-text-2)]">{PROGRESS[index]}</p>
        <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
          This takes about half a minute. Nothing is saved until you approve it.
        </p>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Kontrola a uloženie
-------------------------------------------------------------------------- */

function ReviewCard({
  draft,
  overwrites,
  warnings,
  error,
  applying,
  onApply,
  onRegenerate,
  onBack,
}: {
  draft: PersonaDraft;
  overwrites?: boolean;
  warnings: string[];
  error: string;
  applying: boolean;
  onApply: () => void;
  onRegenerate: () => void;
  onBack: () => void;
}) {
  const { persona, behavior } = draft;
  const spice = choiceOf(SPICE_LEVELS, behavior.heat);
  const slang = choiceOf(SLANG_LEVELS, behavior.slang);

  return (
    <div className="space-y-4">
      <div className="app-card overflow-hidden">
        <div className="border-b border-[var(--app-border)] px-5 py-4">
          <h2 className="text-[14px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
            Here she is
          </h2>
          <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--app-text-3)]">
            {overwrites
              ? "Nothing has been saved yet. Apply it and every field below REPLACES what is on her Persona and Behavior tabs — including anything you wrote yourself. You can still edit all of it afterwards."
              : "Nothing has been saved yet. Apply it and every field below lands on her Persona, Behavior and Voice tabs, where you can edit any of it word by word."}
          </p>
        </div>

        <div className="divide-y divide-[var(--app-border)]">
          <Section title="Who she is">
            <Row label="Name" value={persona.name} />
            <Row label="Age" value={String(persona.age)} />
            <Row label="Lives in" value={persona.city} />
            <Row label="Her time zone" value={behavior.active_tz} />
          </Section>

          <Section title="Her story">
            <Row value={persona.backstory} />
          </Section>

          <Section title="How she talks">
            <Row label="Languages she speaks" value={persona.languages} />
            <Row label="Tone" value={persona.tone} />
            <Row label="Message style" value={persona.msg_style} />
            <Row label="Slang" value={slang ? slang.label : behavior.slang} />
            <Row
              label="Types without accents"
              value={behavior.no_diacritics ? "Yes" : "No"}
            />
            <Row label="Voice notes" value={behavior.voices_enabled ? "On" : "Off"} />
            <Row label="Photos" value={behavior.photos_enabled ? "On" : "Off"} />
          </Section>

          {/* Rytmus je jediná časť draftu, ktorú klient nezadal slovami —
              o to viac ju musí pred zápisom vidieť. */}
          <Section title="Her rhythm">
            <Row
              label="Replies"
              value={`usually in ${behavior.reply_delay_min_s}–${behavior.reply_delay_max_s} s, straight away ${pct(behavior.quick_reply_chance)} of the time`}
            />
            <Row
              label="Leaves it on seen"
              value={`${pct(behavior.seen_only_chance)} of messages, and gets back to it hours later ${pct(behavior.defer_reply_chance)} of the time`}
            />
            <Row label="Asks a question back" value={pct(behavior.question_chance)} />
            <Row
              label="Keeps a chat going"
              value={`${behavior.chat_days} ${behavior.chat_days === 1 ? "day" : "days"}`}
            />
          </Section>

          <Section title="Examples of her writing">
            <Row value={persona.examples} />
          </Section>

          <Section title="Limits">
            <Row label="Spice level" value={spice ? spice.label : behavior.heat} />
            <Row label="What she never does" value={persona.boundaries} />
          </Section>

          <Section title="Your funnel">
            <Row label="Your link" value={persona.cta_link || "None — she never sends a link"} />
            <Row label="How she leads to it" value={persona.funnel_rules} />
            {persona.extra_rules && (
              <Row label="Extra instructions" value={persona.extra_rules} />
            )}
          </Section>
        </div>
      </div>

      {warnings.length > 0 && (
        <Callout>
          <p className="font-medium text-[var(--app-text-2)]">We adjusted a few things:</p>
          <ul className="mt-1.5 list-disc space-y-1 pl-4">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Callout>
      )}

      {error && <Callout tone="danger">{error}</Callout>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <button type="button" onClick={onBack} className="app-btn app-btn-quiet h-9 px-3">
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
          Change my answers
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onRegenerate}
            disabled={applying}
            className="app-btn app-btn-ghost h-9 px-4"
          >
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} />
            Try again
          </button>
          <button
            type="button"
            onClick={onApply}
            disabled={applying}
            className="app-btn app-btn-primary h-9 px-4"
          >
            {applying ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            ) : (
              <Check className="h-3.5 w-3.5" strokeWidth={1.75} />
            )}
            Apply to her tabs
          </button>
        </div>
      </div>
    </div>
  );
}

/** 0.07 → „7%". Percentá sa čítajú, desatinné čísla sa lúštia. */
function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-5 py-4">
      <p className="app-group-label mb-3">{title}</p>
      <dl className="space-y-3">{children}</dl>
    </div>
  );
}

function Row({ label, value }: { label?: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[11rem_1fr] sm:gap-4">
      {label && <dt className="text-[12px] text-[var(--app-text-4)]">{label}</dt>}
      <dd
        className={cn(
          "whitespace-pre-wrap text-[12.5px] leading-relaxed text-[var(--app-text-2)]",
          !label && "sm:col-span-2",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Kroky
-------------------------------------------------------------------------- */

const TITLES = [
  "Who is she?",
  "Where does she live?",
  "What is she like?",
  "Tell us about her life",
  "How does she text?",
  "How far does she go?",
  "How present is she?",
  "Your link, her voice and photos",
];

function Progress({ step }: { step: number }) {
  return (
    <div className="flex items-center gap-3 border-b border-[var(--app-border)] px-5 py-3.5">
      <span className="text-[11px] uppercase tracking-[0.08em] text-[var(--app-text-4)]">
        {step + 1} / {LAST_STEP + 1}
      </span>
      <div className="flex flex-1 gap-1">
        {TITLES.map((title, index) => (
          <span
            key={title}
            className={cn(
              "h-0.5 flex-1 rounded-full transition-colors",
              index <= step ? "bg-[var(--app-text-3)]" : "bg-[var(--app-border)]",
            )}
          />
        ))}
      </div>
    </div>
  );
}

function StepBody({
  step,
  answers,
  set,
}: {
  step: number;
  answers: WizardAnswers;
  set: <K extends keyof WizardAnswers>(key: K, value: WizardAnswers[K]) => void;
}) {
  return (
    <>
      <h2 className="text-[16px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
        {TITLES[step]}
      </h2>

      {step === 0 && (
        <StepBasics answers={answers} set={set} />
      )}
      {step === 1 && <StepHome answers={answers} set={set} />}
      {step === 2 && <StepVibe answers={answers} set={set} />}
      {step === 3 && <StepLife answers={answers} set={set} />}
      {step === 4 && <StepTexting answers={answers} set={set} />}
      {step === 5 && <StepSpice answers={answers} set={set} />}
      {step === 6 && <StepPace answers={answers} set={set} />}
      {step === 7 && <StepFunnel answers={answers} set={set} />}
    </>
  );
}

type StepProps = {
  answers: WizardAnswers;
  set: <K extends keyof WizardAnswers>(key: K, value: WizardAnswers[K]) => void;
};

function StepBasics({ answers, set }: StepProps) {
  const ages = [];
  for (let age = WIZARD_MIN_AGE; age <= WIZARD_MAX_AGE; age++) ages.push(age);

  return (
    <>
      <Hint>The name she introduces herself with, and how old she says she is.</Hint>
      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="wizard-name" className="app-label mb-2">
            Her name
          </label>
          <input
            id="wizard-name"
            className="app-input"
            value={answers.name}
            maxLength={60}
            placeholder="Simona"
            onChange={(event) => set("name", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="wizard-age" className="app-label mb-2">
            Her age
          </label>
          <select
            id="wizard-age"
            className="app-select"
            value={answers.age}
            onChange={(event) => set("age", Number(event.target.value))}
          >
            {ages.map((age) => (
              <option key={age} value={age}>
                {age}
              </option>
            ))}
          </select>
          <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
            Adults only. Older than {WIZARD_MAX_AGE}? Pick anything here and change it on
            the Persona tab, which goes up to 99.
          </p>
        </div>
      </div>
    </>
  );
}

function StepHome({ answers, set }: StepProps) {
  return (
    <>
      <Hint>
        This sets her time zone, so her day, her good nights and her small talk happen at
        the right hour — and it gives her real local detail to talk about.
      </Hint>
      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="wizard-city" className="app-label mb-2">
            City
          </label>
          <input
            id="wizard-city"
            className="app-input"
            value={answers.city}
            maxLength={80}
            placeholder="Los Angeles"
            onChange={(event) => set("city", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="wizard-country" className="app-label mb-2">
            Country
          </label>
          <input
            id="wizard-country"
            className="app-input"
            value={answers.country}
            maxLength={80}
            placeholder="United States"
            onChange={(event) => set("country", event.target.value)}
          />
        </div>
      </div>
    </>
  );
}

function StepVibe({ answers, set }: StepProps) {
  return (
    <>
      <Hint>Pick one or two. This is the first thing a fan feels about her.</Hint>
      <Chips
        className="mt-5"
        options={VIBES}
        selected={answers.vibes}
        max={MAX_VIBES}
        onChange={(values) => set("vibes", values)}
      />
    </>
  );
}

function StepLife({ answers, set }: StepProps) {
  return (
    <>
      <Hint>
        Anything you write here becomes her backstory — a job, studies, a pet, a hobby, how
        she ended up where she lives. A few sentences are enough; the AI fills in the rest.
      </Hint>
      <textarea
        className="app-input mt-5 min-h-[9rem] resize-y py-2.5"
        value={answers.life}
        maxLength={2000}
        placeholder="Studies design, works part time in a coffee place, runs in the mornings and lives alone with a cat. Grew up in a small town and moved to the city two years ago."
        onChange={(event) => set("life", event.target.value)}
      />
      <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
        Optional, but this is the single answer that makes her feel like a person.
      </p>
    </>
  );
}

function StepTexting({ answers, set }: StepProps) {
  return (
    <>
      <Hint>How her messages look on a phone, and what she can read a fan in.</Hint>

      <div className="mt-5 space-y-5">
        <Field label="Slang">
          <Chips
            options={SLANG_LEVELS}
            selected={[answers.slang]}
            max={1}
            onChange={(values) => values[0] && set("slang", values[0])}
          />
        </Field>
        <Field label="Message length">
          <Chips
            options={MSG_LENGTHS}
            selected={[answers.length]}
            max={1}
            onChange={(values) => values[0] && set("length", values[0])}
          />
        </Field>
        <Field label="Emoji">
          <Chips
            options={EMOJI_LEVELS}
            selected={[answers.emoji]}
            max={1}
            onChange={(values) => values[0] && set("emoji", values[0])}
          />
        </Field>
        <Field label="Languages she speaks">
          {/* To isté ovládanie ako na karte Persona — vrátane úrovní. Bez nich
              si model úrovne domýšľal a klientovi potom v nastaveniach chýbal
              jazyk, ktorý si tu vybral. */}
          <LanguageFields
            className=""
            primary={answers.langPrimary}
            extra={answers.langExtra}
            onChange={(primary, extra) => {
              set("langPrimary", primary);
              set("langExtra", extra);
            }}
          />
          <input
            className="app-input mt-3"
            value={answers.languagesNote}
            maxLength={300}
            placeholder="Anything else? e.g. “a little Croatian from summers there”"
            onChange={(event) => set("languagesNote", event.target.value)}
          />
        </Field>
      </div>
    </>
  );
}

function StepSpice({ answers, set }: StepProps) {
  return (
    <>
      <Hint>
        How far she goes in a Telegram chat. Explicit content always stays on your own
        platform — at every level she keeps it at hints and tension here, which is exactly
        what makes a fan want the link.
      </Hint>
      <Chips
        className="mt-5"
        options={SPICE_LEVELS}
        selected={[answers.spice]}
        max={1}
        onChange={(values) => values[0] && set("spice", values[0])}
      />
    </>
  );
}

function StepPace({ answers, set }: StepProps) {
  return (
    <>
      <Hint>
        Two things nobody notices until they are wrong: how fast she answers, and how long
        she stays interested. An agent that replies to everyone in four seconds, forever, is
        the easiest thing in the world to spot.
      </Hint>

      <div className="mt-5 space-y-5">
        <Field label="How fast she replies">
          <Chips
            options={PACE_LEVELS}
            selected={[answers.pace]}
            max={1}
            onChange={(values) => values[0] && set("pace", values[0])}
          />
        </Field>
        <Field label="How long she keeps a chat going">
          <Chips
            options={CHAT_WINDOWS}
            selected={[answers.chatWindow]}
            max={1}
            onChange={(values) => values[0] && set("chatWindow", values[0])}
          />
          <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            Day one is her most talkative; after that she answers less and less, then sends
            one last message pointing at your page and goes quiet. You can change this later
            in Telegram settings.
          </p>
        </Field>
      </div>
    </>
  );
}

function StepFunnel({ answers, set }: StepProps) {
  return (
    <>
      <Hint>Where a warm chat should end up, and whether she talks out loud.</Hint>

      <div className="mt-5 space-y-5">
        <div>
          <label htmlFor="wizard-link" className="app-label mb-2">
            Her link (optional)
          </label>
          <input
            id="wizard-link"
            className="app-input"
            type="url"
            value={answers.link}
            maxLength={300}
            placeholder="https://fanvue.com/yourprofile"
            onChange={(event) => set("link", event.target.value)}
          />
          <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
            Leave it empty and she never sends a link at all. Even with one, she never
            sends it before the sixth message and at most once per fan every 48 hours.
          </p>
        </div>

        <Field label="Voice notes">
          <Chips
            options={[
              {
                value: "yes",
                label: "She sends voice notes",
                hint: "pick her actual voice later on the Voice tab",
                prompt: "",
              },
              { value: "no", label: "Text only", prompt: "" },
            ]}
            selected={[answers.voice ? "yes" : "no"]}
            max={1}
            onChange={(values) => set("voice", values[0] === "yes")}
          />
        </Field>

        <Field label="Photos">
          <Chips
            options={[
              {
                value: "yes",
                label: "She sends photos",
                hint: "upload them later on the Photos tab",
                prompt: "",
              },
              { value: "no", label: "No photos", prompt: "" },
            ]}
            selected={[answers.photos ? "yes" : "no"]}
            max={1}
            onChange={(values) => set("photos", values[0] === "yes")}
          />
        </Field>
      </div>
    </>
  );
}

/* --------------------------------------------------------------------------
   Drobné kúsky
-------------------------------------------------------------------------- */

function Hint({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-[var(--app-text-3)]">
      {children}
    </p>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="app-label mb-2">{label}</p>
      {children}
    </div>
  );
}

/**
 * Čipy. `max={1}` je prepínač (klik na vybraný nič nerobí — inak by sa dalo
 * odkliknúť do stavu „nič", ktorý pri jednovoľbe nemá význam), `max>1` je
 * viacvýber, kde ďalší klik nad limit vytlačí najstarší.
 */
function Chips({
  options,
  selected,
  max,
  onChange,
  className,
}: {
  options: readonly Choice[];
  selected: readonly string[];
  max: number;
  onChange: (values: string[]) => void;
  className?: string;
}) {
  const toggle = (value: string) => {
    if (max === 1) {
      onChange([value]);
      return;
    }
    if (selected.includes(value)) {
      onChange(selected.filter((item) => item !== value));
      return;
    }
    const next = [...selected, value];
    onChange(next.length > max ? next.slice(next.length - max) : next);
  };

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {options.map((option) => {
        const active = selected.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => toggle(option.value)}
            className={cn(
              "app-tap rounded-lg border px-3 py-2 text-left transition-colors",
              active
                ? "border-[var(--app-text-3)] bg-[var(--app-surface-hover)]"
                : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
            )}
          >
            <span className="block text-[12.5px] font-medium text-[var(--app-text)]">
              {option.label}
            </span>
            {option.hint && (
              <span className="mt-0.5 block text-[11px] text-[var(--app-text-4)]">
                {option.hint}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Čo ešte chýba, aby sa dalo pokračovať. Prázdne = krok je hotový. */
function validateStep(step: number, answers: WizardAnswers): string {
  if (step === 0) {
    if (answers.name.trim().length < 2) return "She needs a name.";
    if (answers.age < WIZARD_MIN_AGE || answers.age > WIZARD_MAX_AGE) {
      return "Pick an age.";
    }
  }
  if (step === 1 && !answers.city.trim()) return "Tell us her city.";
  if (step === 2 && answers.vibes.length === 0) return "Pick at least one.";
  if (step === LAST_STEP && answers.link.trim() && !/^https?:\/\/\S+\.\S+/.test(answers.link.trim())) {
    return "That link does not look right.";
  }
  return "";
}

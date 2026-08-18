"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  CheckCircle2,
  KeyRound,
  Loader2,
  MinusCircle,
  Phone,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Zap,
} from "lucide-react";

import {
  cancelLoginJobAction,
  saveApiKeysAction,
  startTelegramLoginAction,
  submitLoginCodeAction,
  submitLoginPasswordAction,
  pollLoginJobAction,
  type ControlBotState,
  type WizardField,
} from "@/app/app/m/[id]/telegram/actions";
import { setModelStatusAction } from "@/app/app/actions";
import { ControlBotCard } from "@/components/app/telegram/control-bot-card";
import { Field } from "@/components/app/telegram/field";
import {
  ActivateGuide,
  ApiKeysGuide,
  CodeGuide,
  PhoneGuide,
} from "@/components/app/telegram/guides";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { isRecent } from "@/lib/format";
import { prettifyCode, statusReasonText } from "@/lib/status";
import type { LoginJob } from "@/lib/telegram";
import { checkApiHash, checkApiId, checkPhone } from "@/lib/telegram-setup";
import { cn } from "@/lib/utils";

/** Fázy, počas ktorých sa oplatí pollovať — worker s nimi ešte niečo robí. */
const LIVE_PHASES: LoginJob["phase"][] = [
  "send_code",
  "code_sent",
  "verify_code",
  "need_password",
  "verify_password",
];

/**
 * Päť krokov, nie štyri.
 *
 * Kontrolný bot tu raz bol, potom sa presunul do Settings — a klientovi po
 * zadaní kódu naskočila rovno aktivácia, takže o bote nikdy nepočul. Je
 * NEPOVINNÝ (odpisovanie na ňom nestojí, `runner.py` ho pri zlyhaní preskočí),
 * ale musí byť VIDIEŤ, s jasným „Skip for now". Nastavenia ho ukazujú tým
 * istým komponentom, aby sa obe obrazovky nemohli rozísť.
 */
const STEPS = [
  { n: 1, label: "API keys", icon: KeyRound },
  { n: 2, label: "Phone", icon: Phone },
  { n: 3, label: "Code", icon: Smartphone },
  { n: 4, label: "Control bot", icon: Bot, optional: true },
  { n: 5, label: "Activate", icon: Zap },
] as const;

const CONTROL_BOT_STEP = 4;
const ACTIVATE_STEP = 5;

export type WizardProps = {
  modelId: string;
  modelName: string;
  status: string;
  statusReason: string;
  apiId: string;
  apiHash: string;
  connected: boolean;
  connectedPhone: string | null;
  controlBot: ControlBotState;
  initialJob: LoginJob | null;
};

export function TelegramWizard(props: WizardProps) {
  const router = useRouter();

  const [job, setJob] = useState<LoginJob | null>(props.initialJob);
  const [connected, setConnected] = useState(props.connected);
  const [reconnecting, setReconnecting] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const [apiId, setApiId] = useState(props.apiId);
  const [apiHash, setApiHash] = useState(props.apiHash);
  const [phone, setPhone] = useState(props.connectedPhone ?? "");

  /**
   * ULOŽENÝ stav kľúčov — nie to, čo je práve v políčkach.
   *
   * Toto je jadro opravy klamúceho steppera: krok 1 doteraz posúval iba
   * `localStep`, takže „API keys ✓" svietilo zelenou, hoci v `models` bolo
   * `tg_api_id NULL` a prázdny hash. Fajka teraz svieti len podľa hodnôt,
   * ktoré server naozaj zapísal (`saveApiKeysAction` ich vráti a zároveň
   * prídu z DB v propsoch pri každom refreshi).
   */
  const [stored, setStored] = useState({ apiId: props.apiId, apiHash: props.apiHash });
  const [controlBot, setControlBot] = useState(props.controlBot);
  const [botSkipped, setBotSkipped] = useState(false);

  const [localStep, setLocalStep] = useState(() => {
    if (props.status === "active") return ACTIVATE_STEP;
    if (props.connected) return props.controlBot.paired ? ACTIVATE_STEP : CONTROL_BOT_STEP;
    return props.apiId && props.apiHash ? 2 : 1;
  });

  const [error, setError] = useState<{ message: string; field?: WizardField } | null>(null);
  const [pending, startTransition] = useTransition();

  const live = Boolean(job && LIVE_PHASES.includes(job.phase));
  // Čerstvo spadnutý pokus musí ostať na obrazovke aj keď už polling skončil —
  // inak by sa wizard ticho vrátil na formulár a klient by nevedel prečo.
  const showFailedJob = Boolean(
    job && job.phase === "error" && isRecent(job.updated_at, 30 * 60_000),
  );

  // Worker beží každé 2 s — rovnakým tempom sa pýtame na stav.
  useEffect(() => {
    if (!live) return;
    let cancelled = false;

    const tick = async () => {
      const result = await pollLoginJobAction(props.modelId);
      if (cancelled) return;
      setJob(result.job);
      if (result.connected) {
        setConnected(true);
        setReconnecting(false);
        // Po prihlásení sa ide na kontrolného bota, nie rovno na aktiváciu.
        setLocalStep((step) => (step < CONTROL_BOT_STEP ? CONTROL_BOT_STEP : step));
        router.refresh();
      }
    };

    const timer = window.setInterval(tick, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [live, props.modelId, router]);

  // Sekundová tikačka pre odpočet expirácie
  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [live]);

  const onJobScreen = live || showFailedJob;

  const activeStep = useMemo(() => {
    if (reconnecting || !connected) return onJobScreen ? 3 : Math.min(localStep, 2);
    return Math.max(localStep, CONTROL_BOT_STEP);
  }, [reconnecting, connected, onJobScreen, localStep]);

  const apiKeysStored = Boolean(stored.apiId && stored.apiHash);

  /** Stav každého krúžku v stepperi — čítaný z toho, čo je naozaj uložené. */
  const stepTone = (step: number): "done" | "skipped" | "todo" => {
    if (step === 1) return apiKeysStored ? "done" : "todo";
    if (step === 2 || step === 3) return connected && !reconnecting ? "done" : "todo";
    if (step === CONTROL_BOT_STEP) {
      if (controlBot.paired) return "done";
      return botSkipped ? "skipped" : "todo";
    }
    return props.status === "active" ? "done" : "todo";
  };

  /** Chyba patrí k tomuto políčku? */
  const fieldError = (field: WizardField) =>
    error?.field === field ? error.message : undefined;

  const backToApiKeys = (
    <button
      type="button"
      onClick={() => {
        setError(null);
        // Späť na krok 1 sa u UŽ pripojenej modelky dá dostať len cez
        // „reconnect" — bez toho by `activeStep` hodnotu 1 nikdy nepustil.
        // U nepripojenej sa nič prepínať nemusí (a „Cancel" v pásiku by tam
        // len mýlil).
        if (connected) {
          setReconnecting(true);
          setConnected(false);
        }
        setJob(null);
        setLocalStep(1);
      }}
      className="underline underline-offset-2"
    >
      Back to API keys
    </button>
  );

  /** Chyba z kroku 1, ktorá vyskočila neskôr — nech je vidieť, kam sa vrátiť. */
  const strayApiKeyError =
    error && (error.field === "api_id" || error.field === "api_hash") && activeStep !== 1 ? (
      <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
        {error.message} {backToApiKeys}
      </Callout>
    ) : null;

  const continueFromApiKeys = () => {
    setError(null);
    const idCheck = checkApiId(apiId);
    if (!apiId.trim()) {
      setError({ message: "Fill in api_id from my.telegram.org.", field: "api_id" });
      return;
    }
    if (!idCheck.ok) {
      setError({ message: idCheck.message, field: "api_id" });
      return;
    }
    const hashCheck = checkApiHash(apiHash);
    if (!apiHash.trim()) {
      setError({ message: "Fill in api_hash from my.telegram.org.", field: "api_hash" });
      return;
    }
    if (!hashCheck.ok) {
      setError({ message: hashCheck.message, field: "api_hash" });
      return;
    }

    // Uložiť SKÔR, než sa krok posunie — inak by stepper znova tvrdil niečo,
    // čo v databáze nie je.
    startTransition(async () => {
      const result = await saveApiKeysAction({
        modelId: props.modelId,
        apiId,
        apiHash,
      });
      if (result.error) {
        setError({ message: result.error, field: result.field });
        return;
      }
      setStored({ apiId: apiId.trim(), apiHash: apiHash.trim() });
      setLocalStep(2);
    });
  };

  const startLogin = () => {
    setError(null);
    const phoneCheck = checkPhone(phone);
    if (!phone.trim()) {
      setError({ message: "Enter her phone number.", field: "phone" });
      return;
    }
    if (!phoneCheck.ok) {
      setError({ message: phoneCheck.message, field: "phone" });
      return;
    }
    startTransition(async () => {
      const result = await startTelegramLoginAction({
        modelId: props.modelId,
        apiId,
        apiHash,
        phone,
      });
      if (result.error) {
        setError({ message: result.error, field: result.field });
        return;
      }
      // Job existuje — polling prevezme štafetu.
      const fresh = await pollLoginJobAction(props.modelId);
      setJob(fresh.job);
    });
  };

  const startOver = () => {
    setError(null);
    startTransition(async () => {
      if (job) await cancelLoginJobAction(job.id);
      setJob(null);
      setLocalStep(1);
    });
  };

  return (
    <div className="space-y-5">
      <ConnectionStrip
        connected={connected && !reconnecting}
        phone={props.connectedPhone}
        onReconnect={() => {
          setReconnecting(true);
          setLocalStep(1);
          setJob(null);
        }}
        reconnecting={reconnecting}
        onCancelReconnect={() => setReconnecting(false)}
      />

      <Stepper active={activeStep} tone={stepTone} onJump={setLocalStep} unlocked={connected} />

      {strayApiKeyError}

      <AnimatePresence mode="wait">
        <motion.div
          key={`${activeStep}-${job?.phase ?? "none"}`}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          {activeStep === 1 && (
            <StepApiKeys
              apiId={apiId}
              apiHash={apiHash}
              onApiId={(value) => {
                setApiId(value);
                if (error?.field === "api_id") setError(null);
              }}
              onApiHash={(value) => {
                setApiHash(value);
                if (error?.field === "api_hash") setError(null);
              }}
              onBlurApiId={() => {
                const check = checkApiId(apiId);
                if (!check.ok) setError({ message: check.message, field: "api_id" });
              }}
              onBlurApiHash={() => {
                const check = checkApiHash(apiHash);
                if (!check.ok) setError({ message: check.message, field: "api_hash" });
              }}
              apiIdError={fieldError("api_id")}
              apiHashError={fieldError("api_hash")}
              formError={error && !error.field ? error.message : null}
              pending={pending}
              onContinue={continueFromApiKeys}
            />
          )}

          {activeStep === 2 && (
            <StepPhone
              phone={phone}
              onPhone={(value) => {
                setPhone(value);
                if (error?.field === "phone") setError(null);
              }}
              onBlur={() => {
                const check = checkPhone(phone);
                if (!check.ok) setError({ message: check.message, field: "phone" });
              }}
              pending={pending}
              phoneError={fieldError("phone")}
              formError={error && !error.field ? error.message : null}
              onBack={() => {
                setError(null);
                setLocalStep(1);
              }}
              onSend={startLogin}
            />
          )}

          {activeStep === 3 && job && (
            <StepCode
              // Nový pokus (worker vrátil fázu späť) komponent premountuje —
              // políčko s neplatným kódom sa tým samo vyčistí.
              key={`${job.phase}:${job.error}`}
              job={job}
              now={now}
              pending={pending}
              onStartOver={startOver}
              onSubmitCode={(code) =>
                startTransition(async () => {
                  setError(null);
                  const result = await submitLoginCodeAction(job.id, code);
                  if (result.error) {
                    setError({ message: result.error, field: result.field });
                    return;
                  }
                  const fresh = await pollLoginJobAction(props.modelId);
                  setJob(fresh.job);
                })
              }
              onSubmitPassword={(password) =>
                startTransition(async () => {
                  setError(null);
                  const result = await submitLoginPasswordAction(job.id, password);
                  if (result.error) {
                    setError({ message: result.error, field: result.field });
                    return;
                  }
                  const fresh = await pollLoginJobAction(props.modelId);
                  setJob(fresh.job);
                })
              }
              codeError={fieldError("code")}
              passwordError={fieldError("password")}
              backToApiKeys={backToApiKeys}
            />
          )}

          {activeStep === CONTROL_BOT_STEP && (
            <ControlBotCard
              modelId={props.modelId}
              initial={controlBot}
              onStateChange={setControlBot}
              footer={
                <ControlBotFooter
                  paired={controlBot.paired}
                  onContinue={() => setLocalStep(ACTIVATE_STEP)}
                  onSkip={() => {
                    // „Preskočené" je len navigácia. V DB sa nič nemení, takže
                    // model neostane v polovičnom stave — bot buď je, alebo nie
                    // je, a dorobiť sa dá kedykoľvek v Settings.
                    setBotSkipped(true);
                    setLocalStep(ACTIVATE_STEP);
                  }}
                />
              }
            />
          )}

          {activeStep === ACTIVATE_STEP && (
            <StepActivate
              modelId={props.modelId}
              modelName={props.modelName}
              status={props.status}
              statusReason={props.statusReason}
              controlBotPaired={controlBot.paired}
              onBackToBot={() => setLocalStep(CONTROL_BOT_STEP)}
            />
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Stav pripojenia                                                            */
/* -------------------------------------------------------------------------- */

function ConnectionStrip({
  connected,
  phone,
  onReconnect,
  reconnecting,
  onCancelReconnect,
}: {
  connected: boolean;
  phone: string | null;
  onReconnect: () => void;
  reconnecting: boolean;
  onCancelReconnect: () => void;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border px-5 py-4 sm:flex-row sm:items-center sm:justify-between",
        connected
          ? "border-[rgba(74,222,128,0.24)] bg-[#0c0c0c]"
          : "border-[var(--app-border)] bg-[#0c0c0c]",
      )}
    >
      <div className="flex items-center gap-3">
        <span
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-xl",
            connected ? "bg-[#123a28] text-[#6ee7a8]" : "bg-[#141414] text-[var(--app-text-3)]",
          )}
        >
          {connected ? (
            <CheckCircle2 className="h-4.5 w-4.5" />
          ) : (
            <Smartphone className="h-4.5 w-4.5" />
          )}
        </span>
        <div>
          <p className="text-[13.5px] font-semibold text-white">
            {connected ? "Telegram connected" : "Telegram not connected"}
          </p>
          <p className="text-[12.5px] text-[var(--app-text-3)]">
            {connected
              ? phone
                ? `Signed in as ${phone}`
                : "Her account is signed in."
              : "She cannot reply to anyone until her account is signed in."}
          </p>
        </div>
      </div>

      {connected ? (
        <button
          type="button"
          onClick={onReconnect}
          className="app-btn app-btn-ghost h-9 shrink-0 px-4"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Reconnect
        </button>
      ) : reconnecting ? (
        <button
          type="button"
          onClick={onCancelReconnect}
          className="app-btn app-btn-ghost h-9 shrink-0 px-4"
        >
          Cancel
        </button>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Stepper                                                                     */
/* -------------------------------------------------------------------------- */

function Stepper({
  active,
  tone,
  onJump,
  unlocked,
}: {
  active: number;
  tone: (step: number) => "done" | "skipped" | "todo";
  onJump: (step: number) => void;
  /** Po pripojení sa smie klikať medzi botom a aktiváciou. */
  unlocked: boolean;
}) {
  return (
    <ol className="flex items-center gap-1 overflow-x-auto pb-1">
      {STEPS.map((step, index) => {
        const state = tone(step.n);
        const current = step.n === active;
        const Icon = step.icon;
        const clickable = unlocked && step.n >= CONTROL_BOT_STEP && !current;

        return (
          <li key={step.n} className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onJump(step.n)}
              title={
                state === "skipped"
                  ? "Skipped — you can add the control bot any time"
                  : undefined
              }
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
                clickable && "cursor-pointer hover:border-[var(--app-border-strong)]",
                current
                  ? "border-[var(--app-border-strong)] bg-[var(--app-active)] text-[var(--app-text)]"
                  : state === "done"
                    ? "border-[rgba(74,222,128,0.28)] bg-[#0c0c0c] text-[#86efac]"
                    : state === "skipped"
                      ? "border-[var(--app-border)] bg-[#0c0c0c] text-[var(--app-text-3)]"
                      : "border-[var(--app-border)] bg-[#0c0c0c] text-[var(--app-text-4)]",
              )}
            >
              {!current && state === "done" ? (
                <CheckCircle2 className="h-3.5 w-3.5" />
              ) : !current && state === "skipped" ? (
                <MinusCircle className="h-3.5 w-3.5" />
              ) : (
                <Icon className="h-3.5 w-3.5" />
              )}
              <span className="hidden sm:inline">
                {step.label}
                {"optional" in step && step.optional && state === "todo" && !current && (
                  <span className="ml-1 text-[10.5px] text-[var(--app-text-4)]">optional</span>
                )}
              </span>
              <span className="sm:hidden">{step.n}</span>
            </button>
            {index < STEPS.length - 1 && <span className="h-px w-3 bg-[#26262a] sm:w-5" />}
          </li>
        );
      })}
    </ol>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 1 — api_id / api_hash                                                 */
/* -------------------------------------------------------------------------- */

function StepApiKeys({
  apiId,
  apiHash,
  onApiId,
  onApiHash,
  onBlurApiId,
  onBlurApiHash,
  onContinue,
  apiIdError,
  apiHashError,
  formError,
  pending,
}: {
  apiId: string;
  apiHash: string;
  onApiId: (value: string) => void;
  onApiHash: (value: string) => void;
  onBlurApiId: () => void;
  onBlurApiHash: () => void;
  onContinue: () => void;
  apiIdError?: string;
  apiHashError?: string;
  formError: string | null;
  pending: boolean;
}) {
  return (
    <Card>
      <CardHeader
        title="Telegram API keys"
        description="Telegram gives every account its own app keys. You do this once per model, signed in as her."
      />
      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_1fr]">
        <ApiKeysGuide />

        <div className="space-y-4">
          <Field
            label="api_id"
            value={apiId}
            onChange={onApiId}
            onBlur={onBlurApiId}
            placeholder="1234567"
            inputMode="numeric"
            error={apiIdError}
            hint="Digits only — the shorter of the two values."
          />
          <Field
            label="api_hash"
            value={apiHash}
            onChange={onApiHash}
            onBlur={onBlurApiHash}
            placeholder="0123456789abcdef0123456789abcdef"
            mono
            error={apiHashError}
            hint="32 characters, digits and letters a–f."
          />
          {formError && (
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              {formError}
            </Callout>
          )}
          <Callout tone="neutral">
            We store these encrypted and use them only to keep her account online.
          </Callout>
          <button
            type="button"
            onClick={onContinue}
            disabled={pending}
            className="app-btn app-btn-primary h-10 w-full"
          >
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            Save and continue
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 2 — telefón                                                            */
/* -------------------------------------------------------------------------- */

function StepPhone({
  phone,
  onPhone,
  onBlur,
  onSend,
  onBack,
  pending,
  phoneError,
  formError,
}: {
  phone: string;
  onPhone: (value: string) => void;
  onBlur: () => void;
  onSend: () => void;
  onBack: () => void;
  pending: boolean;
  phoneError?: string;
  formError: string | null;
}) {
  return (
    <Card>
      <CardHeader
        title="Her phone number"
        description="Telegram sends a login code to this account — have the phone (or her Telegram app) at hand."
      />
      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_1fr]">
        <PhoneGuide />

        <div className="space-y-4">
          <Field
            label="Phone number"
            value={phone}
            onChange={onPhone}
            onBlur={onBlur}
            placeholder="+421901234567"
            inputMode="tel"
            error={phoneError}
            hint="International format, country code included."
          />

          {formError && (
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              {formError}
            </Callout>
          )}

          <Callout tone="gold" icon={<ShieldCheck className="h-3.5 w-3.5" />}>
            Use a dedicated number, not your personal one. Telegram does not love userbots on
            heavily used personal accounts.
          </Callout>

          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={onSend}
              disabled={pending}
              className="app-btn app-btn-primary h-10 px-5"
            >
              {pending && <Loader2 className="h-4 w-4 animate-spin" />}
              Send code
            </button>
            <button type="button" onClick={onBack} className="app-btn app-btn-ghost h-10 px-5">
              Back
            </button>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 3 — kód / 2FA / čakanie                                               */
/* -------------------------------------------------------------------------- */

function StepCode({
  job,
  now,
  pending,
  codeError,
  passwordError,
  onSubmitCode,
  onSubmitPassword,
  onStartOver,
  backToApiKeys,
}: {
  job: LoginJob;
  now: number;
  pending: boolean;
  codeError?: string;
  passwordError?: string;
  onSubmitCode: (code: string) => void;
  onSubmitPassword: (password: string) => void;
  onStartOver: () => void;
  backToApiKeys: React.ReactNode;
}) {
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");

  const jobError = job.error ? loginErrorText(job.error) : null;
  const expiresIn = Math.max(0, new Date(job.expires_at).getTime() - now);
  const stale = now - new Date(job.updated_at).getTime() > 25_000;

  const waiting =
    job.phase === "send_code" || job.phase === "verify_code" || job.phase === "verify_password";

  const waitingText: Record<string, string> = {
    send_code: "Asking Telegram to send the code…",
    verify_code: "Checking the code…",
    verify_password: "Checking her password…",
  };

  return (
    <Card>
      <CardHeader
        title={
          job.phase === "error"
            ? "Login failed"
            : job.phase === "need_password"
              ? "Two-step password"
              : "Login code"
        }
        description={
          job.phase === "error"
            ? `Telegram did not let us in with ${job.phone}.`
            : job.phase === "need_password"
              ? "This account has two-step verification switched on."
              : `Telegram sent a code to ${job.phone}. It arrives in her Telegram app, or by SMS if she is not signed in anywhere.`
        }
      />

      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_1fr]">
        <CodeGuide />

        <div className="space-y-4">
          {job.phase === "error" ? (
            <>
              <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
                {jobError?.body ?? "The login attempt failed."}{" "}
                {/* Chyba na kroku 3, ktorej príčina je na kroku 1 — nech je
                    vidieť, kam sa vrátiť, a nie len „start over". */}
                {jobError?.blamesApiKeys ? backToApiKeys : null}
              </Callout>
              <button
                type="button"
                onClick={onStartOver}
                className="app-btn app-btn-primary h-10 px-5"
              >
                Start over
              </button>
            </>
          ) : waiting ? (
            <div className="flex items-center gap-3 rounded-xl border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-5">
              <Loader2 className="h-4.5 w-4.5 animate-spin text-[var(--app-text-2)]" />
              <div>
                <p className="text-[13.5px] text-[var(--app-text-2)]">{waitingText[job.phase]}</p>
                {stale && (
                  <p className="mt-1 text-[12px] text-[var(--app-text-4)]">
                    Taking longer than usual. If nothing happens within a minute, start over.
                  </p>
                )}
              </div>
            </div>
          ) : job.phase === "need_password" ? (
            <div className="space-y-3">
              <Field
                label="Two-step password"
                value={password}
                onChange={setPassword}
                type="password"
                placeholder="Her Telegram password"
                error={passwordError}
                hint="Her Telegram cloud password. Used only for this sign-in."
              />
              <button
                type="button"
                onClick={() => onSubmitPassword(password)}
                disabled={pending || !password}
                className="app-btn app-btn-primary h-10 w-full"
              >
                {pending && <Loader2 className="h-4 w-4 animate-spin" />}
                Confirm password
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <Field
                label="Login code"
                value={code}
                onChange={(value) => setCode(value.replace(/\D/g, "").slice(0, 8))}
                placeholder="12345"
                inputMode="numeric"
                mono
                error={codeError}
                hint="Five digits, from the chat named Telegram."
              />
              <button
                type="button"
                onClick={() => onSubmitCode(code)}
                disabled={pending || code.length < 4}
                className="app-btn app-btn-primary h-10 w-full"
              >
                {pending && <Loader2 className="h-4 w-4 animate-spin" />}
                Confirm code
              </button>
            </div>
          )}

          {job.phase !== "error" && jobError && (
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              {jobError.body} {jobError.blamesApiKeys ? backToApiKeys : null}
            </Callout>
          )}

          {job.phase !== "error" && (
            <div className="flex items-center justify-between gap-3 border-t border-[var(--app-border)] pt-4 text-[12px] text-[var(--app-text-4)]">
              <span>
                {expiresIn > 0
                  ? `This attempt expires in ${formatCountdown(expiresIn)}.`
                  : "This attempt has expired."}
              </span>
              <button
                type="button"
                onClick={onStartOver}
                className="text-[var(--app-text-3)] underline underline-offset-2 transition-colors hover:text-[var(--app-text)]"
              >
                Start over
              </button>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 4 — kontrolný bot (nepovinný)                                          */
/* -------------------------------------------------------------------------- */

function ControlBotFooter({
  paired,
  onContinue,
  onSkip,
}: {
  paired: boolean;
  onContinue: () => void;
  onSkip: () => void;
}) {
  return (
    <div className="space-y-2 border-t border-[var(--app-border)] pt-4">
      <div className="flex flex-wrap items-center gap-2.5">
        <button
          type="button"
          onClick={onContinue}
          className={cn("app-btn h-10 px-5", paired ? "app-btn-primary" : "app-btn-ghost")}
        >
          Continue
          <ArrowRight className="h-4 w-4" />
        </button>
        {!paired && (
          <button type="button" onClick={onSkip} className="app-btn app-btn-primary h-10 px-5">
            Skip for now
          </button>
        )}
      </div>
      <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        She will reply to fans either way. You can add the control bot later in Settings.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 5 — aktivácia                                                          */
/* -------------------------------------------------------------------------- */

function StepActivate({
  modelId,
  modelName,
  status,
  statusReason,
  controlBotPaired,
  onBackToBot,
}: {
  modelId: string;
  modelName: string;
  status: string;
  statusReason: string;
  controlBotPaired: boolean;
  onBackToBot: () => void;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [justActivated, setJustActivated] = useState(false);

  const activate = () => {
    setError(null);
    startTransition(async () => {
      const result = await setModelStatusAction(modelId, "active");
      if (result.error) {
        setError(result.error);
        return;
      }
      setJustActivated(true);
      router.refresh();
    });
  };

  const isLive = status === "active";

  return (
    <Card gold>
      <CardHeader
        title={isLive ? `${modelName} is live` : "Ready to go live"}
        description={
          isLive
            ? "She is signed in, configured and answering fans."
            : "Everything is in place. Switch her on whenever you are ready."
        }
      />
      <div className="space-y-4 p-5">
        <ul className="space-y-2 text-[13px] text-[var(--app-text-2)]">
          <Ready>Telegram account connected</Ready>
          <Ready>Persona and behaviour can be tuned any time, no restart needed</Ready>
          {controlBotPaired && <Ready>Control bot paired — notifications go to your Telegram</Ready>}
        </ul>

        {/* Bez kontrolného bota odpisuje ďalej (`runner.py` ho preskočí), ale
            majiteľ o novom fanúšikovi nevie a nemá ako prevziať chat. Nie je to
            teda prekážka aktivácie — je to vec, ktorú treba povedať nahlas. */}
        {!controlBotPaired && (
          <Callout tone="gold">
            You skipped the control bot, so nothing will ping you about new fans and you cannot
            take over a chat from your phone. She still replies.{" "}
            <button type="button" onClick={onBackToBot} className="underline underline-offset-2">
              Set it up now
            </button>
            , or later in{" "}
            <Link
              href={`/app/m/${modelId}/telegram/settings`}
              className="underline underline-offset-2"
            >
              Settings
            </Link>
            .
          </Callout>
        )}

        {error && (
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
          </Callout>
        )}

        {/* `statusReasonText`, nie `prettifyCode`: dôvod má byť pokyn, nie kód.
            `bad_config:tg_api_id` sa tu prečíta ako veta o chýbajúcom api_id. */}
        {statusReason && !isLive && (
          <Callout tone="danger">{statusReasonText(statusReason)}</Callout>
        )}

        {isLive || justActivated ? (
          <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
            She comes online within 30 seconds and answers new DMs from that moment on. Message
            her from another Telegram account to see it work.
          </Callout>
        ) : (
          <button
            type="button"
            onClick={activate}
            disabled={pending}
            className="app-btn app-btn-primary h-10 px-5"
          >
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            Activate {modelName}
          </button>
        )}

        <ActivateGuide />

        <div className="flex flex-wrap gap-4 border-t border-[var(--app-border)] pt-4 text-[12.5px]">
          <Link
            href={`/app/m/${modelId}/persona`}
            className="text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
          >
            Set up her persona →
          </Link>
          <Link
            href={`/app/m/${modelId}/telegram/settings`}
            className="text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
          >
            {controlBotPaired ? "Change control bot" : "Add a control bot"}
          </Link>
        </div>
      </div>
    </Card>
  );
}

function Ready({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2.5">
      <CheckCircle2 className="mt-px h-4 w-4 shrink-0 text-[#6ee7a8]" />
      {children}
    </li>
  );
}

/* -------------------------------------------------------------------------- */
/*  Drobnosti                                                                   */
/* -------------------------------------------------------------------------- */

/** `154200` → `1 h 47 min`, `95` → `1 min 35 s`. */
function formatSeconds(seconds: number): string {
  if (seconds >= 3600) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.round((seconds % 3600) / 60);
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
  }
  if (seconds >= 60) {
    const minutes = Math.floor(seconds / 60);
    return `${minutes} min ${seconds % 60} s`;
  }
  return `${seconds} s`;
}

function formatCountdown(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * Chybové kódy z workera (`login_jobs._error_code`) → vety pre klienta.
 *
 * Kód sa nikdy neukazuje taký, aký je: `flood_wait_600` klientovi nič nepovie,
 * kým „Telegram ťa brzdí, počkaj 10 minút" povie všetko. `blamesApiKeys`
 * označuje tie, ktorých príčina leží na prvom kroku — wizard k nim doloží odkaz
 * späť ku kľúčom, aby sa hláška nedala prečítať pod nesprávnym políčkom.
 */
export function loginErrorText(code: string): { body: string; blamesApiKeys?: boolean } {
  const flood = /^flood_wait_(\d+)$/.exec(code);
  if (flood) {
    return {
      body: `Telegram is rate-limiting this number. Wait ${formatSeconds(
        Number(flood[1]),
      )} and try again — trying sooner only extends the wait.`,
    };
  }

  switch (code) {
    case "invalid_code":
      return { body: "That code was not right. Type it again — the same code still works." };
    case "invalid_password":
      return { body: "That password did not match. Try again." };
    case "expired":
      return { body: "This attempt timed out after 10 minutes. Start over to get a new code." };
    case "phone_code_expired":
      return { body: "The code expired. Start over and Telegram will send a fresh one." };
    case "phone_code_invalid":
      return { body: "Telegram rejected that code. Start over and use the newest one." };
    case "api_id_invalid":
      return {
        body:
          "Telegram did not accept the api_id and api_hash pair. Check both on my.telegram.org — " +
          "the api_id is the short number, the api_hash the 32-character line.",
        blamesApiKeys: true,
      };
    case "phone_number_invalid":
      return { body: "Telegram does not know that phone number. Check the country code." };
    case "phone_number_banned":
      return { body: "Telegram has banned this number. It cannot be used for an agent." };
    case "decrypt_failed":
      return {
        body: "We could not read the encrypted data. Start over — if it happens again, contact us.",
      };
    default:
      return { body: `Telegram said: ${prettifyCode(code)}. Start over and try again.` };
  }
}

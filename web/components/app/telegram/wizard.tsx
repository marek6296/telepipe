"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Loader2,
  Phone,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Zap,
} from "lucide-react";

import {
  cancelLoginJobAction,
  startTelegramLoginAction,
  submitLoginCodeAction,
  submitLoginPasswordAction,
  pollLoginJobAction,
} from "@/app/app/m/[id]/telegram/actions";
import { setModelStatusAction } from "@/app/app/actions";
import { Field } from "@/components/app/telegram/field";
import { ApiKeysGuide } from "@/components/app/telegram/guides";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { isRecent } from "@/lib/format";
import { prettifyCode } from "@/lib/status";
import type { LoginJob } from "@/lib/telegram";
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
 * Sprievodca pripája ÚČET modelky — nič viac. Kontrolný bot tu bol piatym
 * krokom, ale je to nastavenie majiteľa (a mení sa aj rok po spustení), takže
 * má vlastnú obrazovku: Telegram → Settings. Odpisovanie na ňom nestojí —
 * `runner.py` ho pri zlyhaní preskočí a odpisuje ďalej.
 */
const STEPS = [
  { n: 1, label: "API keys", icon: KeyRound },
  { n: 2, label: "Phone", icon: Phone },
  { n: 3, label: "Code", icon: Smartphone },
  { n: 4, label: "Activate", icon: Zap },
];

export type WizardProps = {
  modelId: string;
  modelName: string;
  status: string;
  statusReason: string;
  apiId: string;
  apiHash: string;
  connected: boolean;
  connectedPhone: string | null;
  controlBotReady: boolean;
  initialJob: LoginJob | null;
};

export function TelegramWizard(props: WizardProps) {
  const router = useRouter();

  const [job, setJob] = useState<LoginJob | null>(props.initialJob);
  const [connected, setConnected] = useState(props.connected);
  const [reconnecting, setReconnecting] = useState(false);
  const [localStep, setLocalStep] = useState(props.apiId && props.apiHash ? 2 : 1);
  const [now, setNow] = useState(() => Date.now());

  const [apiId, setApiId] = useState(props.apiId);
  const [apiHash, setApiHash] = useState(props.apiHash);
  const [phone, setPhone] = useState(props.connectedPhone ?? "");

  const [error, setError] = useState<string | null>(null);
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
    if (reconnecting) return onJobScreen ? 3 : localStep;
    if (!connected) return onJobScreen ? 3 : localStep;
    return 4;
  }, [reconnecting, connected, onJobScreen, localStep]);

  const startLogin = () => {
    setError(null);
    startTransition(async () => {
      const result = await startTelegramLoginAction({
        modelId: props.modelId,
        apiId,
        apiHash,
        phone,
      });
      if (result.error) {
        setError(result.error);
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

      <Stepper active={activeStep} connected={connected} />

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
              onApiId={setApiId}
              onApiHash={setApiHash}
              error={error}
              onContinue={() => {
                setError(null);
                if (!apiId.trim() || !apiHash.trim()) {
                  setError("Fill in both api_id and api_hash to continue.");
                  return;
                }
                setLocalStep(2);
              }}
            />
          )}

          {activeStep === 2 && (
            <StepPhone
              phone={phone}
              onPhone={setPhone}
              pending={pending}
              error={error}
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
                    setError(result.error);
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
                    setError(result.error);
                    return;
                  }
                  const fresh = await pollLoginJobAction(props.modelId);
                  setJob(fresh.job);
                })
              }
              error={error}
            />
          )}

          {activeStep === 4 && (
            <StepActivate
              modelId={props.modelId}
              modelName={props.modelName}
              status={props.status}
              statusReason={props.statusReason}
              controlBotReady={props.controlBotReady}
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

function Stepper({ active, connected }: { active: number; connected: boolean }) {
  return (
    <ol className="flex items-center gap-1 overflow-x-auto pb-1">
      {STEPS.map((step, index) => {
        const done = (step.n <= 3 && connected) || step.n < active;
        const current = step.n === active;
        const Icon = step.icon;
        return (
          <li key={step.n} className="flex shrink-0 items-center gap-1">
            <div
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
                current
                  ? "border-[var(--app-border-strong)] bg-[var(--app-active)] text-[var(--app-text)]"
                  : done
                    ? "border-[rgba(74,222,128,0.28)] bg-[#0c0c0c] text-[#86efac]"
                    : "border-[var(--app-border)] bg-[#0c0c0c] text-[var(--app-text-4)]",
              )}
            >
              {done && !current ? (
                <CheckCircle2 className="h-3.5 w-3.5" />
              ) : (
                <Icon className="h-3.5 w-3.5" />
              )}
              <span className="hidden sm:inline">{step.label}</span>
              <span className="sm:hidden">{step.n}</span>
            </div>
            {index < STEPS.length - 1 && (
              <span className="h-px w-3 bg-[#26262a] sm:w-5" />
            )}
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
  onContinue,
  error,
}: {
  apiId: string;
  apiHash: string;
  onApiId: (value: string) => void;
  onApiHash: (value: string) => void;
  onContinue: () => void;
  error: string | null;
}) {
  return (
    <Card>
      <CardHeader
        title="Telegram API keys"
        description="Telegram gives every account its own app keys. You only do this once per model."
      />
      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_1fr]">
        <ApiKeysGuide />

        <div className="space-y-4">
          <Field
            label="api_id"
            value={apiId}
            onChange={onApiId}
            placeholder="1234567"
            inputMode="numeric"
          />
          <Field
            label="api_hash"
            value={apiHash}
            onChange={onApiHash}
            placeholder="0123456789abcdef0123456789abcdef"
            mono
          />
          {error && (
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              {error}
            </Callout>
          )}
          <Callout tone="neutral">
            We store these encrypted and use them only to keep her account online.
          </Callout>
          <button type="button" onClick={onContinue} className="app-btn app-btn-primary h-10 w-full">
            Continue
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
  onSend,
  onBack,
  pending,
  error,
}: {
  phone: string;
  onPhone: (value: string) => void;
  onSend: () => void;
  onBack: () => void;
  pending: boolean;
  error: string | null;
}) {
  return (
    <Card>
      <CardHeader
        title="Her phone number"
        description="Telegram sends a login code to this account — have the phone (or her Telegram app) at hand."
      />
      <div className="space-y-4 p-5">
        <div className="max-w-sm">
          <Field
            label="Phone number"
            value={phone}
            onChange={onPhone}
            placeholder="+421901234567"
            inputMode="tel"
          />
          <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
            International format, including the country code.
          </p>
        </div>

        {error && (
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
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
  error,
  onSubmitCode,
  onSubmitPassword,
  onStartOver,
}: {
  job: LoginJob;
  now: number;
  pending: boolean;
  error: string | null;
  onSubmitCode: (code: string) => void;
  onSubmitPassword: (password: string) => void;
  onStartOver: () => void;
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
    verify_password: "Checking your password…",
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

      <div className="space-y-4 p-5">
        {job.phase === "error" ? (
          <>
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              {jobError?.body ?? "The login attempt failed."}
            </Callout>
            <button type="button" onClick={onStartOver} className="app-btn app-btn-primary h-10 px-5">
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
          <div className="max-w-sm space-y-3">
            <Field
              label="Two-step password"
              value={password}
              onChange={setPassword}
              type="password"
              placeholder="Her Telegram password"
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
          <div className="max-w-sm space-y-3">
            <Field
              label="Login code"
              value={code}
              onChange={(value) => setCode(value.replace(/\D/g, "").slice(0, 8))}
              placeholder="12345"
              inputMode="numeric"
              mono
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
            {jobError.body}
          </Callout>
        )}

        {error && (
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
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
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 4 — aktivácia                                                          */
/* -------------------------------------------------------------------------- */

function StepActivate({
  modelId,
  modelName,
  status,
  statusReason,
  controlBotReady,
}: {
  modelId: string;
  modelName: string;
  status: string;
  statusReason: string;
  controlBotReady: boolean;
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
        </ul>

        {/* Bez kontrolného bota odpisuje ďalej (`runner.py` ho preskočí), ale
            majiteľ o novom fanúšikovi nevie a nemá ako prevziať chat. Nie je to
            teda prekážka aktivácie — je to vec, ktorú treba povedať nahlas. */}
        {!controlBotReady && (
          <Callout tone="gold">
            No control bot yet, so nothing will ping you about new fans and you cannot take
            over a chat from your phone. She still replies.{" "}
            <Link
              href={`/app/m/${modelId}/telegram/settings`}
              className="underline underline-offset-2"
            >
              Set it up in Settings
            </Link>
            .
          </Callout>
        )}

        {error && (
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
          </Callout>
        )}

        {statusReason && !isLive && (
          <Callout tone="danger">{prettifyCode(statusReason)}</Callout>
        )}

        {isLive || justActivated ? (
          <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
            Your agent starts within 30 seconds. New DMs get answered from that moment on.
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
            {controlBotReady ? "Change control bot" : "Add a control bot"}
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
 * Neznámy kód aspoň zľudštíme, nech tam nesvieti `phone_number_banned`.
 */
export function loginErrorText(code: string): { body: string } {
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
        body: "Telegram rejected the api_id / api_hash pair. Check them on my.telegram.org and start over.",
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

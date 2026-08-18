"use client";

import { useEffect, useState, useTransition, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Copy, Loader2, RefreshCw } from "lucide-react";

import {
  createPairingCodeAction,
  pollControlBotAction,
  saveControlBotAction,
  unlinkControlBotAction,
  type ControlBotState,
} from "@/app/app/m/[id]/telegram/actions";
import { Field } from "@/components/app/telegram/field";
import { ControlBotGuide } from "@/components/app/telegram/guides";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { checkBotToken, checkChatId } from "@/lib/telegram-setup";

/**
 * Kontrolný bot — token, párovanie kódom, ručná záloha.
 *
 * JEDEN KOMPONENT PRE DVE MIESTA. Je to štvrtý krok sprievodcu (klient si bota
 * vyrobí hneď, kým je v tom) aj karta v Telegram → Settings (bot sa mení aj rok
 * po spustení: nový telefón, iný účet, revoknutý token). Boli to dve obrazovky
 * s vlastnou kópiou textu a to je presne to, čo sa rozíde — preto je tu jeden
 * komponent a rozdiel je len `footer`, ktorý si dodá sprievodca.
 *
 * PÁROVANIE MIESTO OPISOVANIA ČÍSLA. Dashboard vydá jednorazový kód, klient ho
 * pošle svojmu botovi, bot si z tej správy zoberie chat id a zapíše ho ako
 * majiteľa. Predtým sa chat id opisovalo ručne z @userinfobota a preklep sa
 * nedal odhaliť: `control_bot.py` púšťa každý handler len majiteľovi, takže pri
 * zlom čísle bot mlčal aj na `/start`. Ručné zadanie ostáva zabalené v
 * „Advanced" — Marek chce obe cesty.
 *
 * Token sa do políčka NIKDY nepredvyplní: je šifrovaný a von už nejde. Prázdne
 * pole preto znamená „nechaj ten, čo tam je", nie „zmaž ho".
 */
export function ControlBotCard({
  modelId,
  initial,
  footer,
  onStateChange,
}: {
  modelId: string;
  initial: ControlBotState;
  /** Sprievodca sem dá „Skip for now" a „Continue"; nastavenia nič. */
  footer?: ReactNode;
  onStateChange?: (state: ControlBotState) => void;
}) {
  const router = useRouter();
  const [state, setState] = useState(initial);
  const [token, setToken] = useState("");
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [chatId, setChatId] = useState("");
  const [chatIdError, setChatIdError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [copied, setCopied] = useState(false);

  const apply = (next: ControlBotState) => {
    setState(next);
    onStateChange?.(next);
  };

  // Kým čaká kód, sa pýtame na stav — spárovanie sa deje v Telegrame, takže
  // dashboard sa to inak nemá ako dozvedieť. Po spárovaní sa polling zastaví.
  const waitingForCode = Boolean(state.pending) && !state.paired;
  useEffect(() => {
    if (!waitingForCode) return;
    let cancelled = false;

    const timer = window.setInterval(async () => {
      const fresh = await pollControlBotAction(modelId);
      if (cancelled) return;
      setState(fresh);
      onStateChange?.(fresh);
      if (fresh.paired) router.refresh();
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // `onStateChange` je zo sprievodcu a mení sa pri každom rendere — do
    // závislostí nesmie, inak by sa interval reštartoval donekonečna.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waitingForCode, modelId, router]);

  const saveToken = () => {
    const check = checkBotToken(token);
    if (!check.ok) {
      setTokenError(check.message);
      return;
    }
    const manual = chatId.trim();
    if (manual) {
      const chatCheck = checkChatId(manual);
      if (!chatCheck.ok) {
        setChatIdError(chatCheck.message);
        return;
      }
    }
    setError(null);
    setNotice(null);
    setTokenError(null);
    setChatIdError(null);

    startTransition(async () => {
      const result = await saveControlBotAction({ modelId, token, ownerChatId: manual });
      if (result.error) {
        if (result.field === "token") setTokenError(result.error);
        else if (result.field === "chat_id") setChatIdError(result.error);
        else setError(result.error);
        return;
      }
      setToken("");
      setChatId("");
      setNotice(
        result.detail ? `Saved. ${result.detail} is your control bot.` : "Bot token saved.",
      );
      apply(await pollControlBotAction(modelId));
      router.refresh();
    });
  };

  const generateCode = () => {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      const result = await createPairingCodeAction(modelId);
      if (result.error) {
        setError(result.error);
        return;
      }
      apply({ ...state, pending: result.code ?? null });
    });
  };

  const unlink = () => {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      const result = await unlinkControlBotAction(modelId);
      if (result.error) {
        setError(result.error);
        return;
      }
      apply(await pollControlBotAction(modelId));
      router.refresh();
    });
  };

  const copy = async () => {
    if (!state.pending) return;
    try {
      await navigator.clipboard.writeText(state.pending.code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Bez povolenia na schránku ostáva kód na obrazovke — dá sa prepísať.
    }
  };

  return (
    <Card>
      <CardHeader
        title="Your control bot"
        description="A small Telegram bot of your own. It tells you when a new fan writes, and gives you a menu to steer her from your own Telegram. It is optional — she replies to fans either way."
      />
      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_1fr]">
        <ControlBotGuide />

        <div className="space-y-4">
          {state.paired ? (
            <>
              <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
                Connected as{" "}
                <span className="font-medium">
                  {state.ownerLabel ?? `chat ${state.ownerChatId}`}
                </span>
                . Notifications and the menu go to that chat.
              </Callout>
              <button
                type="button"
                onClick={unlink}
                disabled={pending}
                className="app-btn app-btn-ghost h-9 px-4"
              >
                {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Unlink
              </button>
            </>
          ) : (
            <>
              <Field
                label="Bot token"
                value={token}
                onChange={(value) => {
                  setToken(value);
                  if (tokenError) setTokenError(null);
                }}
                onBlur={() => {
                  const check = checkBotToken(token);
                  setTokenError(check.ok ? null : check.message);
                }}
                placeholder={
                  state.hasToken ? "Leave empty to keep the saved token" : "123456789:AAE…"
                }
                mono
                type="password"
                error={tokenError}
                hint="The whole line from BotFather, digits then a colon then letters."
              />

              {state.hasToken && (
                <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
                  A token is already saved. Leave the field empty unless you replaced the bot.
                </Callout>
              )}

              {state.hasToken ? (
                state.pending ? (
                  <PairingCodePanel
                    code={state.pending.code}
                    expiresAt={state.pending.expiresAt}
                    copied={copied}
                    onCopy={copy}
                    onRegenerate={generateCode}
                    pending={pending}
                  />
                ) : (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={generateCode}
                      disabled={pending}
                      className="app-btn app-btn-primary h-10 w-full"
                    >
                      {pending && <Loader2 className="h-4 w-4 animate-spin" />}
                      Generate pairing code
                    </button>
                    <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
                      You send the code to your bot in Telegram. It answers, remembers your chat,
                      and that is the whole pairing.
                    </p>
                  </div>
                )
              ) : (
                <button
                  type="button"
                  onClick={saveToken}
                  disabled={pending || !token}
                  className="app-btn app-btn-primary h-10 w-full"
                >
                  {pending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Save bot token
                </button>
              )}

              {state.hasToken && token && (
                <button
                  type="button"
                  onClick={saveToken}
                  disabled={pending}
                  className="app-btn app-btn-ghost h-9 w-full"
                >
                  Replace saved token
                </button>
              )}

              {/* Ručná cesta ostáva, len sa už nikomu neplietie pod ruky. */}
              <details className="group rounded-lg border border-[var(--app-border)] bg-[#0c0c0c]">
                <summary className="cursor-pointer list-none px-3.5 py-2.5 text-[12px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]">
                  Advanced: type the chat ID myself
                </summary>
                <div className="space-y-3 border-t border-[var(--app-border)] px-3.5 py-3">
                  <p className="text-[12px] leading-relaxed text-[var(--app-text-4)]">
                    Open{" "}
                    <a
                      href="https://t.me/userinfobot"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline underline-offset-2"
                    >
                      @userinfobot
                    </a>{" "}
                    from your own Telegram, press Start, and copy the number it replies with. A
                    typo here is silent — the bot simply never answers you — so pairing by code is
                    the safer route.
                  </p>
                  <Field
                    label="Your chat ID"
                    value={chatId}
                    onChange={(value) => {
                      setChatId(value.replace(/[^\d-]/g, ""));
                      if (chatIdError) setChatIdError(null);
                    }}
                    onBlur={() => {
                      const check = checkChatId(chatId);
                      setChatIdError(check.ok ? null : check.message);
                    }}
                    placeholder="566608217"
                    inputMode="numeric"
                    error={chatIdError}
                  />
                  <button
                    type="button"
                    onClick={saveToken}
                    disabled={pending || (!chatId && !token) || (!state.hasToken && !token)}
                    className="app-btn app-btn-ghost h-9 w-full"
                  >
                    {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Save chat ID
                  </button>
                </div>
              </details>
            </>
          )}

          {error && (
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              {error}
            </Callout>
          )}
          {notice && !error && (
            <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
              {notice}
            </Callout>
          )}

          <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            The token is encrypted before it touches our database, and it never leaves the server
            again.
          </p>

          {footer}
        </div>
      </div>
    </Card>
  );
}

function PairingCodePanel({
  code,
  expiresAt,
  copied,
  onCopy,
  onRegenerate,
  pending,
}: {
  code: string;
  expiresAt: string;
  copied: boolean;
  onCopy: () => void;
  onRegenerate: () => void;
  pending: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const left = Math.max(0, new Date(expiresAt).getTime() - now);
  const minutes = Math.floor(left / 60_000);
  const seconds = Math.floor((left % 60_000) / 1000);
  const expired = left <= 0;

  return (
    <div className="space-y-3 rounded-lg border border-[var(--app-border-strong)] bg-[#0e0e0e] p-4">
      <p className="text-[12.5px] leading-relaxed text-[var(--app-text-2)]">
        Send this to your bot in Telegram, as a normal message:
      </p>
      <div className="flex items-center gap-2">
        <span className="flex-1 rounded-md bg-[#161616] px-3 py-2.5 text-center font-mono text-[18px] tracking-[0.18em] text-white">
          {code}
        </span>
        <button
          type="button"
          onClick={onCopy}
          className="app-btn app-btn-ghost h-10 shrink-0 px-3"
          aria-label="Copy pairing code"
        >
          {copied ? <CheckCircle2 className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
      <div className="flex items-center justify-between gap-3 text-[11.5px] text-[var(--app-text-4)]">
        <span className="inline-flex items-center gap-2">
          {!expired && <Loader2 className="h-3 w-3 animate-spin" />}
          {expired
            ? "This code expired."
            : `Waiting for your bot — expires in ${minutes}:${String(seconds).padStart(2, "0")}.`}
        </span>
        <button
          type="button"
          onClick={onRegenerate}
          disabled={pending}
          className="inline-flex items-center gap-1 underline underline-offset-2 transition-colors hover:text-[var(--app-text)]"
        >
          <RefreshCw className="h-3 w-3" />
          New code
        </button>
      </div>
    </div>
  );
}

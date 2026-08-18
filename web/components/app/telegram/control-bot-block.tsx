"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import {
  pollControlBotAction,
  removeControlBotAction,
  saveControlBotAction,
  type ControlBotState,
} from "@/app/app/m/[id]/telegram/actions";
import { BlockDetails, TelegramBlock } from "@/components/app/telegram/block";
import { Field } from "@/components/app/telegram/field";
import { ControlBotGuide } from "@/components/app/telegram/guides";
import { Callout } from "@/components/app/ui";
import { checkBotToken } from "@/lib/telegram-setup";

/**
 * BLOK 2 — tvoj kontrolný bot. Len bot, nič iné.
 *
 * Tento blok zodpovedá za JEDNU vec: či je uložený token z @BotFathera. Komu
 * ten bot píše, rieši blok 3 a je to zámerne inde. Kým to bola jedna karta,
 * spárovaný stav ju celú zbalil do „Connected as X" a rozdiel medzi „mám bota"
 * a „bot vie, komu písať" prestal existovať — nedalo sa zmeniť jedno bez
 * druhého a nedalo sa ani prečítať, čo z toho je nastavené.
 *
 * Token sa do políčka NIKDY nepredvyplní: je šifrovaný a von už nejde. Prázdne
 * pole preto znamená „nechaj ten, čo tam je", nie „zmaž ho" — mazanie má
 * vlastné tlačidlo s potvrdením.
 */
export function ControlBotBlock({
  modelId,
  state,
  onState,
  index,
}: {
  modelId: string;
  state: ControlBotState;
  onState: (next: ControlBotState) => void;
  index?: number;
}) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [replacing, setReplacing] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [pending, startTransition] = useTransition();

  const refresh = async () => {
    onState(await pollControlBotAction(modelId));
    router.refresh();
  };

  const saveToken = () => {
    // Server je autorita, ale preklep sa má ozvať tu a hneď — nie po výlete
    // do Telegramu a späť.
    const check = checkBotToken(token);
    if (!check.ok) {
      setTokenError(check.message);
      return;
    }
    setError(null);
    setNotice(null);
    setTokenError(null);

    startTransition(async () => {
      const result = await saveControlBotAction({ modelId, token });
      if (result.error) {
        if (result.field === "token") setTokenError(result.error);
        else setError(result.error);
        return;
      }
      setToken("");
      setReplacing(false);
      setNotice(result.detail ? `Saved. ${result.detail} is your control bot.` : "Bot token saved.");
      await refresh();
    });
  };

  const removeBot = () => {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      const result = await removeControlBotAction(modelId);
      if (result.error) {
        setError(result.error);
        return;
      }
      setConfirmRemove(false);
      setNotice("The bot was removed. She keeps replying to fans exactly as before.");
      await refresh();
    });
  };

  const setUp = state.hasToken;
  const showForm = !setUp || replacing;

  return (
    <TelegramBlock
      index={index}
      title="Your control bot"
      optional
      status={setUp ? "on" : "off"}
      statusLabel={setUp ? "Bot token saved" : "Not set up"}
      statusDetail={setUp ? (state.botLabel ?? "the token is stored, encrypted") : null}
      unlocks="A small Telegram bot of your own that watches her account. On its own it stays quiet — it starts writing once you pair your private Telegram in the next block."
    >
      {showForm ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <ControlBotGuide />

          <div className="space-y-4">
            <Field
              label="Bot token"
              value={token}
              onChange={(value) => {
                setToken(value);
                if (tokenError) setTokenError(null);
              }}
              onBlur={() => {
                const check = checkBotToken(token);
                setTokenError(token && !check.ok ? check.message : null);
              }}
              placeholder="123456789:AAE…"
              mono
              type="password"
              error={tokenError}
              hint="The whole line from BotFather, digits then a colon then letters."
            />
            <div className="flex flex-wrap gap-2.5">
              <button
                type="button"
                onClick={saveToken}
                disabled={pending || !token}
                className="app-btn app-btn-primary h-10 px-5"
              >
                {pending && <Loader2 className="h-4 w-4 animate-spin" />}
                {setUp ? "Replace the token" : "Save bot token"}
              </button>
              {replacing && (
                <button
                  type="button"
                  onClick={() => {
                    setReplacing(false);
                    setToken("");
                    setTokenError(null);
                  }}
                  className="app-btn app-btn-ghost h-10 px-5"
                >
                  Cancel
                </button>
              )}
            </div>
            <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
              The token is encrypted before it touches our database, and it never leaves the
              server again. That is also why the field above is always empty.
            </p>
          </div>
        </div>
      ) : (
        <>
          <p className="text-[12.5px] leading-relaxed text-[var(--app-text-2)]">
            {state.botLabel
              ? `${state.botLabel} is the bot we talk to.`
              : "A bot token is stored for this model."}{" "}
            Replace it if you revoked the token in @BotFather or swapped the bot for another one.
          </p>

          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={() => setReplacing(true)}
              className="app-btn app-btn-ghost h-9 px-4"
            >
              Replace token
            </button>
            <button
              type="button"
              onClick={() => setConfirmRemove(true)}
              className="app-btn app-btn-ghost h-9 px-4"
            >
              Remove bot
            </button>
          </div>

          {confirmRemove && (
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              <p>
                Removing the bot deletes the stored token and unpairs your private Telegram with
                it — a bot without a token cannot deliver anything. Her account stays signed in
                and she keeps replying to every fan.
              </p>
              <div className="mt-3 flex flex-wrap gap-2.5">
                <button
                  type="button"
                  onClick={removeBot}
                  disabled={pending}
                  className="app-btn app-btn-ghost h-9 px-4"
                >
                  {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Yes, remove the bot
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmRemove(false)}
                  className="app-btn app-btn-ghost h-9 px-4"
                >
                  Keep it
                </button>
              </div>
            </Callout>
          )}

          <BlockDetails summary="Where the token comes from">
            <ControlBotGuide />
          </BlockDetails>
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
    </TelegramBlock>
  );
}

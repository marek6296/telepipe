"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Copy, Loader2, RefreshCw } from "lucide-react";

import {
  createPairingCodeAction,
  pollControlBotAction,
  saveControlBotAction,
  setOwnerAsClientAction,
  unlinkControlBotAction,
  wipeTestChatAction,
  type ControlBotState,
} from "@/app/app/m/[id]/telegram/actions";
import { Switch } from "@/components/app/forms/fields";
import { BlockDetails, TelegramBlock } from "@/components/app/telegram/block";
import { Field } from "@/components/app/telegram/field";
import { PairingGuide } from "@/components/app/telegram/guides";
import { Callout } from "@/components/app/ui";
import { checkChatId } from "@/lib/telegram-setup";

/**
 * BLOK 3 — tvoj súkromný Telegram.
 *
 * Toto je to, čo v pôvodnej obrazovke nebolo vidieť: bot (blok 2) a účet, do
 * ktorého ten bot píše, sú dve nezávislé veci. Niektorí klienti svoj osobný účet
 * pripoja, iní nie a všetko riešia z účtu, na ktorom modelka beží. Preto má tento
 * blok vlastný stav, vlastné odpojenie a vlastné dôsledky.
 *
 * ČO SEM PATRÍ NAVYŠE. `owner_chat_id` neurčuje len adresáta notifikácií — je to
 * zároveň jediný chat, ktorý sa smie vymazať. Prepínač „odpisuje aj mne"
 * (`models.owner_as_client`) z neho spraví bežný fanúšikovský chat, a mazanie
 * potom vráti presne ten jeden chat na nulu. Obe veci teda visia na spárovaní a
 * bez neho nemajú zmysel — preto sú tu, a nie v bloku 2 ani v Settings.
 */
export function PrivateTelegramBlock({
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
  const [chatId, setChatId] = useState("");
  const [chatIdError, setChatIdError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pending, startTransition] = useTransition();

  const refresh = async () => {
    onState(await pollControlBotAction(modelId));
    router.refresh();
  };

  // Kým čaká kód, pýtame sa na stav — spárovanie sa deje v Telegrame, takže
  // dashboard sa to inak nemá ako dozvedieť. Po spárovaní sa polling zastaví.
  const waitingForCode = Boolean(state.pending) && !state.paired;
  useEffect(() => {
    if (!waitingForCode) return;
    let cancelled = false;

    const timer = window.setInterval(async () => {
      const fresh = await pollControlBotAction(modelId);
      if (cancelled) return;
      onState(fresh);
      if (fresh.paired) router.refresh();
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // `onState` je z rodiča a mení sa pri každom rendere — do závislostí nesmie,
    // inak by sa interval reštartoval donekonečna.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waitingForCode, modelId, router]);

  const generateCode = () => {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      const result = await createPairingCodeAction(modelId);
      if (result.error) {
        setError(result.error);
        return;
      }
      onState({ ...state, pending: result.code ?? null });
    });
  };

  const saveChatId = () => {
    const check = checkChatId(chatId);
    if (!chatId.trim() || !check.ok) {
      setChatIdError(check.ok ? "Type the number @userinfobot replied with." : check.message);
      return;
    }
    setError(null);
    setNotice(null);
    setChatIdError(null);
    startTransition(async () => {
      // Prázdny token = „nechaj ten, čo je uložený" — mení sa len chat id.
      const result = await saveControlBotAction({ modelId, token: "", ownerChatId: chatId });
      if (result.error) {
        if (result.field === "chat_id") setChatIdError(result.error);
        else setError(result.error);
        return;
      }
      setChatId("");
      await refresh();
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
      setNotice("Unpaired. The bot is still saved — pair it again from any Telegram account.");
      await refresh();
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

  const owner = state.ownerLabel ?? (state.ownerChatId ? `chat ${state.ownerChatId}` : null);

  const status = state.paired ? "on" : state.hasToken ? "off" : "waiting";
  const statusLabel = state.paired
    ? "Paired"
    : state.hasToken
      ? "Not paired"
      : "Waiting for the control bot";

  return (
    <TelegramBlock
      index={index}
      title="Your private Telegram"
      optional
      status={status}
      statusLabel={statusLabel}
      statusDetail={state.paired ? owner : null}
      unlocks="The Telegram account the bot writes to. Pair it and the notifications and the menu arrive on your own phone — and your own chat becomes the one test chat you are allowed to wipe."
    >
      {!state.hasToken ? (
        <Callout tone="neutral">
          Set up your control bot in the block above first. The pairing code is a message you send
          to that bot, so without it there is nothing to send it to.
        </Callout>
      ) : !state.paired ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <PairingGuide />

          <div className="space-y-4">
            {state.pending ? (
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
                  You send the code to your bot in Telegram. It answers, remembers your chat, and
                  that is the whole pairing.
                </p>
              </div>
            )}

            {/* Ručná cesta ostáva, len sa už nikomu neplietie pod ruky. */}
            <BlockDetails summary="Advanced: type the chat ID myself">
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
                from your own Telegram, press Start, and copy the number it replies with. A typo
                here is silent — the bot simply never answers you — so pairing by code is the
                safer route.
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
                onClick={saveChatId}
                disabled={pending || !chatId}
                className="app-btn app-btn-ghost h-9 w-full"
              >
                {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Save chat ID
              </button>
            </BlockDetails>
          </div>
        </div>
      ) : (
        <>
          <p className="text-[12.5px] leading-relaxed text-[var(--app-text-2)]">
            Every new fan is announced in {owner}, and the bot menu there lets you read a chat,
            take it over and hand it back.
          </p>

          <TestChatToggle
            modelId={modelId}
            value={state.ownerAsClient}
            onValue={(next) => onState({ ...state, ownerAsClient: next })}
            onError={setError}
          />

          <WipeTestChat modelId={modelId} owner={owner ?? "your chat"} />

          <div className="flex flex-wrap gap-2.5 border-t border-[var(--app-border)] pt-4">
            <button
              type="button"
              onClick={unlink}
              disabled={pending}
              className="app-btn app-btn-ghost h-9 px-4"
            >
              {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Unpair this Telegram
            </button>
          </div>
          <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            Unpairing keeps the bot. Use it when you want the notifications on a different
            Telegram account — unpair here, then pair again from that one.
          </p>
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

/* -------------------------------------------------------------------------- */
/*  „Odpisuje aj mne" — models.owner_as_client                                 */
/* -------------------------------------------------------------------------- */

/**
 * Prepínač, ktorý existoval v databáze od migrácie 006, ale v UI nikdy nebol.
 * Simona aj Mio ho majú roky zapnutý — nastavoval sa ručne v SQL.
 *
 * Zmena si vyžiada tiché prevzatie modelky odznova (`TenantConfig` sa skladá pri
 * claime), takže sa to hovorí nahlas: do pol minúty, session ostáva.
 */
function TestChatToggle({
  modelId,
  value,
  onValue,
  onError,
}: {
  modelId: string;
  value: boolean;
  onValue: (next: boolean) => void;
  onError: (message: string | null) => void;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  const toggle = (next: boolean) => {
    onError(null);
    // Optimisticky — vypínač musí reagovať okamžite, inak sa naň klikne dvakrát.
    onValue(next);
    startTransition(async () => {
      const result = await setOwnerAsClientAction(modelId, next);
      if (result.error) {
        onValue(!next);
        onError(result.error);
        return;
      }
      router.refresh();
    });
  };

  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-[var(--app-text)]">She also replies to you</p>
          <p
            id="owner-as-client-help"
            className="mt-1 max-w-lg text-[12px] leading-relaxed text-[var(--app-text-3)]"
          >
            Off, your messages are treated as commands and she stays silent in your chat. On, your
            chat counts as a normal fan chat: she answers you the way she answers them, and that
            chat becomes the test chat you can wipe below.
          </p>
        </div>
        <Switch
          checked={value}
          onCheckedChange={toggle}
          disabled={pending}
          label="She also replies to you"
          describedBy="owner-as-client-help"
        />
      </div>
      <p className="mt-2.5 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        Changing this picks her up again within half a minute. Her Telegram session is not touched,
        so nothing signs in again and no fan waits longer than usual.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Vymazanie testovacieho chatu                                               */
/* -------------------------------------------------------------------------- */

/**
 * To isté tlačidlo, aké má menu kontrolného bota — len tu ho je vidieť aj ten,
 * kto do Telegramu nechodí. Server action `wipeTestChatAction` neberie žiadne
 * `tg_id`: číslo si vždy prečíta z `models.owner_chat_id`, takže z prehliadača
 * sa cudzí chat vymazať nedá ani pri upravenom requeste.
 */
function WipeTestChat({ modelId, owner }: { modelId: string; owner: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const wipe = () => {
    setError(null);
    startTransition(async () => {
      const result = await wipeTestChatAction(modelId);
      if (result.error) {
        setError(result.error);
        return;
      }
      setConfirming(false);
      setDone(result.deleted ?? 0);
      router.refresh();
    });
  };

  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3.5">
      <p className="text-[13px] font-medium text-[var(--app-text)]">Wipe the test chat</p>
      <p className="mt-1 max-w-lg text-[12px] leading-relaxed text-[var(--app-text-3)]">
        Puts your own conversation with her back to zero, so you can try her out from a clean
        start. Nobody else&apos;s chat is affected.
      </p>

      {done !== null && (
        <div className="mt-3">
          <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
            Wiped — {done} {done === 1 ? "message" : "messages"} removed. Write to her from{" "}
            {owner} and she starts as if you had never spoken.
          </Callout>
        </div>
      )}

      {error && (
        <div className="mt-3">
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
          </Callout>
        </div>
      )}

      {confirming ? (
        <div className="mt-3">
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            <p className="font-medium">Wipe the conversation with {owner}?</p>
            <p className="mt-1.5">This deletes, for that one chat only:</p>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
              <li>every message, hers and yours</li>
              <li>the record of which photos and voice notes she already sent you</li>
              <li>
                everything she remembers about you — facts, episodes, promises she made, things
                she said about herself
              </li>
              <li>the counters: message count, funnel stage, summary, her note on your style</li>
            </ul>
            <p className="mt-1.5">
              No other conversation is touched, and no photo, voice or persona setting is deleted.
              Her account stays signed in and she keeps answering everyone else the whole time.
              This cannot be undone.
            </p>
            <div className="mt-3 flex flex-wrap gap-2.5">
              <button
                type="button"
                onClick={wipe}
                disabled={pending}
                className="app-btn app-btn-ghost h-9 px-4"
              >
                {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Yes, wipe this one chat
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="app-btn app-btn-ghost h-9 px-4"
              >
                Cancel
              </button>
            </div>
          </Callout>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            setDone(null);
            setError(null);
            setConfirming(true);
          }}
          className="app-btn app-btn-ghost mt-3 h-9 px-4"
        >
          Wipe the test chat
        </button>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Párovací kód                                                               */
/* -------------------------------------------------------------------------- */

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

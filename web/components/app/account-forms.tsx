"use client";

import { useActionState, useId, useState, useTransition } from "react";
import { AudioLines, CheckCircle2, ExternalLink, LogOut, Unlink } from "lucide-react";

import {
  changePasswordAction,
  connectElevenAction,
  disconnectElevenAction,
  signOutEverywhereAction,
} from "@/app/app/account/actions";
import {
  AppErrorMessage,
  AppNoticeMessage,
  AppPasswordField,
  AppSubmitButton,
} from "@/components/app/forms/parts";

/** Zmena hesla — staré heslo overujeme cez signInWithPassword. */
export function ChangePasswordForm() {
  const [state, formAction] = useActionState(changePasswordAction, undefined);

  return (
    <form action={formAction} className="max-w-sm space-y-4 p-5">
      <AppPasswordField
        label="Current password"
        name="current"
        autoComplete="current-password"
      />
      <AppPasswordField
        label="New password"
        name="password"
        autoComplete="new-password"
        hint="At least 8 characters."
      />
      <AppPasswordField
        label="Repeat new password"
        name="confirm"
        autoComplete="new-password"
      />

      {state?.error && <AppErrorMessage>{state.error}</AppErrorMessage>}
      {state?.notice && <AppNoticeMessage>{state.notice}</AppNoticeMessage>}

      <AppSubmitButton>Change password</AppSubmitButton>
    </form>
  );
}

/** Odhlásenie všade — jedno tlačidlo, žiadny stav. */
export function SignOutEverywhereButton() {
  return (
    <form action={signOutEverywhereAction}>
      <button type="submit" className="app-btn app-btn-ghost h-9 px-4">
        <LogOut className="h-3.5 w-3.5" strokeWidth={1.75} />
        Sign out everywhere
      </button>
    </form>
  );
}

/**
 * Pripojenie ElevenLabs účtu.
 *
 * Kľúč sa nikdy nevykresľuje späť — server ho ani nemá odkiaľ vziať. Von ide
 * iba `connected` z `has_account_eleven_key()`, takže „•••••" by tu bola
 * ozdoba predstierajúca, že vieme, čo tam je.
 */
export function ElevenLabsCard({ connected }: { connected: boolean }) {
  const id = useId();
  const [state, formAction] = useActionState(connectElevenAction, undefined);
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState<string | null>(null);

  const disconnect = () => {
    setFailed(null);
    startTransition(async () => {
      const result = await disconnectElevenAction();
      if (result?.error) setFailed(result.error);
    });
  };

  return (
    <div className="space-y-5 p-5">
      <div className="flex flex-wrap items-center gap-2.5">
        {connected ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(74,222,128,0.28)] px-2.5 py-1 text-[11px] font-medium text-[#86efac]">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Connected
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--app-border-strong)] px-2.5 py-1 text-[11px] font-medium text-[var(--app-text-3)]">
            <AudioLines className="h-3.5 w-3.5" strokeWidth={1.75} />
            Not connected
          </span>
        )}
        <span className="text-[12px] text-[var(--app-text-4)]">
          One key covers every model on this account.
        </span>
      </div>

      <form action={formAction} className="max-w-sm space-y-4">
        <div>
          <label htmlFor={id} className="app-label mb-2">
            {connected ? "Replace the API key" : "ElevenLabs API key"}
          </label>
          <input
            id={id}
            name="eleven_key"
            type="password"
            required
            autoComplete="off"
            spellCheck={false}
            placeholder="sk_…"
            className="app-input font-mono"
          />
          <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            From your ElevenLabs profile, under API keys. It is encrypted before
            it reaches our database and never shown again — not even to you.
          </p>
        </div>

        {state?.error && <AppErrorMessage>{state.error}</AppErrorMessage>}
        {state?.notice && <AppNoticeMessage>{state.notice}</AppNoticeMessage>}

        <AppSubmitButton>{connected ? "Replace key" : "Connect ElevenLabs"}</AppSubmitButton>
      </form>

      <div className="flex flex-wrap items-center gap-2.5">
        <a
          href="https://elevenlabs.io/app/settings/api-keys"
          target="_blank"
          rel="noreferrer noopener"
          className="app-btn app-btn-ghost h-9 px-4"
        >
          <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} />
          Get a key
        </a>
        {connected && (
          <button
            type="button"
            onClick={disconnect}
            disabled={pending}
            className="app-btn app-btn-ghost h-9 px-4"
          >
            <Unlink className="h-3.5 w-3.5" strokeWidth={1.75} />
            Disconnect
          </button>
        )}
      </div>

      {failed && (
        <p role="alert" className="text-[11.5px] text-[#fca5a5]">
          {failed}
        </p>
      )}
    </div>
  );
}

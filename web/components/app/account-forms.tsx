"use client";

import { useActionState } from "react";
import { LogOut } from "lucide-react";

import { changePasswordAction, signOutEverywhereAction } from "@/app/app/account/actions";
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

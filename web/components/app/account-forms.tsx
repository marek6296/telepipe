"use client";

import { useActionState } from "react";
import { LogOut } from "lucide-react";

import { changePasswordAction, signOutEverywhereAction } from "@/app/app/account/actions";
import {
  ErrorMessage,
  NoticeMessage,
  PasswordField,
  SubmitButton,
} from "@/components/auth/form-parts";

/** Zmena hesla — staré heslo overujeme cez signInWithPassword. */
export function ChangePasswordForm() {
  const [state, formAction] = useActionState(changePasswordAction, undefined);

  return (
    <form action={formAction} className="max-w-sm space-y-4 p-5">
      <PasswordField
        label="Current password"
        name="current"
        autoComplete="current-password"
      />
      <PasswordField
        label="New password"
        name="password"
        autoComplete="new-password"
        hint="At least 8 characters."
      />
      <PasswordField
        label="Repeat new password"
        name="confirm"
        autoComplete="new-password"
      />

      {state?.error && <ErrorMessage>{state.error}</ErrorMessage>}
      {state?.notice && <NoticeMessage>{state.notice}</NoticeMessage>}

      <SubmitButton className="h-11">Change password</SubmitButton>
    </form>
  );
}

/** Odhlásenie všade — jedno tlačidlo, žiadny stav. */
export function SignOutEverywhereButton() {
  return (
    <form action={signOutEverywhereAction}>
      <button type="submit" className="btn-modern-dark h-10 px-5 text-[13px]">
        <LogOut className="h-4 w-4" />
        Sign out everywhere
      </button>
    </form>
  );
}

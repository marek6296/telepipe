"use client";

import { useActionState } from "react";
import Link from "next/link";

import {
  requestPasswordResetAction,
  updatePasswordAction,
  type AuthState,
} from "@/app/(auth)/actions";
import {
  ErrorMessage,
  Field,
  NoticeMessage,
  PasswordField,
  SubmitButton,
} from "@/components/auth/form-parts";

/** Krok 1 — pošli reset link na email. */
export function RequestResetForm() {
  const [state, formAction] = useActionState<AuthState | undefined, FormData>(
    requestPasswordResetAction,
    undefined,
  );

  return (
    <div>
      <h1 className="animate-element animate-delay-200 text-[clamp(1.8rem,3.6vw,2.4rem)] font-semibold leading-tight text-balance-tight">
        <span className="text-gradient-white">Reset password</span>
      </h1>
      <p className="animate-element animate-delay-300 mt-2.5 text-[14.5px] text-white/45">
        Enter your email and we will send you a link to set a new password.
      </p>

      <form action={formAction} className="mt-9 space-y-5">
        {state?.error && (
          <div className="animate-element">
            <ErrorMessage>{state.error}</ErrorMessage>
          </div>
        )}
        {state?.notice && (
          <div className="animate-element">
            <NoticeMessage>{state.notice}</NoticeMessage>
          </div>
        )}

        <div className="animate-element animate-delay-400">
          <Field
            label="Email address"
            name="email"
            type="email"
            placeholder="you@agency.com"
            autoComplete="email"
            defaultValue={state?.email}
          />
        </div>

        <div className="animate-element animate-delay-500">
          <SubmitButton>Send reset link</SubmitButton>
        </div>
      </form>

      <p className="animate-element animate-delay-600 mt-8 text-center text-[13.5px] text-white/45">
        Remembered it?{" "}
        <Link
          href="/login"
          className="font-semibold text-[var(--gold)] transition-colors hover:text-[var(--gold-light)]"
        >
          Back to sign in
        </Link>
      </p>
    </div>
  );
}

/** Krok 2 — nastavenie nového hesla (po kliknutí na link z emailu). */
export function UpdatePasswordForm() {
  const [state, formAction] = useActionState<AuthState | undefined, FormData>(
    updatePasswordAction,
    undefined,
  );

  return (
    <div>
      <h1 className="animate-element animate-delay-200 text-[clamp(1.8rem,3.6vw,2.4rem)] font-semibold leading-tight text-balance-tight">
        <span className="text-gradient-white">Set a new password</span>
      </h1>
      <p className="animate-element animate-delay-300 mt-2.5 text-[14.5px] text-white/45">
        Choose a password you have not used on Telepipe before.
      </p>

      <form action={formAction} className="mt-9 space-y-5">
        {state?.error && (
          <div className="animate-element">
            <ErrorMessage>{state.error}</ErrorMessage>
          </div>
        )}

        <div className="animate-element animate-delay-400">
          <PasswordField
            label="New password"
            name="password"
            autoComplete="new-password"
            hint="At least 8 characters."
          />
        </div>

        <div className="animate-element animate-delay-500">
          <PasswordField
            label="Confirm new password"
            name="confirm"
            autoComplete="new-password"
          />
        </div>

        <div className="animate-element animate-delay-600">
          <SubmitButton>Update password</SubmitButton>
        </div>
      </form>
    </div>
  );
}

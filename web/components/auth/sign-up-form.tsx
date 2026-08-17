"use client";

import { useActionState } from "react";
import Link from "next/link";
import { MailCheck } from "lucide-react";

import { signUpAction, type AuthState } from "@/app/(auth)/actions";
import { GoogleButton } from "@/components/auth/google-button";
import {
  ErrorMessage,
  Field,
  OrDivider,
  PasswordField,
  SubmitButton,
} from "@/components/auth/form-parts";

export function SignUpForm() {
  const [state, formAction] = useActionState<AuthState | undefined, FormData>(
    signUpAction,
    undefined,
  );

  // Po registrácii so zapnutým email confirmom Supabase nevráti session
  if (state?.awaitingConfirmation) {
    return <CheckYourEmail email={state.email} />;
  }

  return (
    <div>
      <h1 className="animate-element animate-delay-200 text-[clamp(1.8rem,3.6vw,2.4rem)] font-semibold leading-tight text-balance-tight">
        <span className="text-gradient-white">Create your account</span>
      </h1>
      <p className="animate-element animate-delay-300 mt-2.5 text-[14.5px] text-white/45">
        Start with a test balance — no card required.
      </p>

      <form action={formAction} className="mt-9 space-y-5">
        {state?.error && (
          <div className="animate-element">
            <ErrorMessage>{state.error}</ErrorMessage>
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
          <PasswordField
            label="Password"
            name="password"
            autoComplete="new-password"
            hint="At least 8 characters."
          />
        </div>

        <div className="animate-element animate-delay-600">
          <PasswordField
            label="Confirm password"
            name="confirm"
            autoComplete="new-password"
          />
        </div>

        <label className="animate-element animate-delay-700 flex cursor-pointer items-start gap-2.5 text-[12.5px] leading-relaxed text-white/50">
          <input
            type="checkbox"
            name="terms"
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-white/20 bg-white/5 accent-[var(--gold)]"
          />
          I agree to run only accounts I am authorised to operate, and to
          Telepipe&apos;s usage-based billing.
        </label>

        <div className="animate-element animate-delay-800">
          <SubmitButton>Create account</SubmitButton>
        </div>
      </form>

      <div className="animate-element animate-delay-900 mt-7">
        <OrDivider label="or sign up with" />
      </div>

      <div className="animate-element animate-delay-1000 mt-5">
        <GoogleButton label="Sign up with Google" />
      </div>

      <p className="animate-element animate-delay-1100 mt-8 text-center text-[13.5px] text-white/45">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-semibold text-[var(--gold)] transition-colors hover:text-[var(--gold-light)]"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}

function CheckYourEmail({ email }: { email?: string }) {
  return (
    <div className="animate-element text-center">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-[rgba(212,175,55,0.28)] bg-[rgba(212,175,55,0.09)]">
        <MailCheck className="h-6 w-6 text-[var(--gold)]" />
      </span>
      <h1 className="mt-7 text-[clamp(1.6rem,3.2vw,2.1rem)] font-semibold leading-tight">
        <span className="text-gradient-gold">Check your email</span>
      </h1>
      <p className="mx-auto mt-4 max-w-sm text-[14.5px] leading-relaxed text-white/50">
        We sent a confirmation link{email ? " to " : ""}
        {email && <span className="font-medium text-white/80">{email}</span>}. Click
        it to activate your account, then sign in.
      </p>
      <p className="mx-auto mt-4 max-w-sm text-[12.5px] leading-relaxed text-white/30">
        Nothing in your inbox after a minute? Check spam — the confirmation is sent
        by Supabase on our behalf.
      </p>
      <Link href="/login" className="btn-modern-dark mt-8 h-12 w-full text-[14px]">
        Back to sign in
      </Link>
    </div>
  );
}

"use client";

import { useActionState } from "react";
import Link from "next/link";

import { signInAction, type AuthState } from "@/app/(auth)/actions";
import { GoogleButton } from "@/components/auth/google-button";
import {
  ErrorMessage,
  Field,
  OrDivider,
  PasswordField,
  SubmitButton,
} from "@/components/auth/form-parts";

export function SignInForm({ next }: { next?: string }) {
  const [state, formAction] = useActionState<AuthState | undefined, FormData>(
    signInAction,
    undefined,
  );

  return (
    <div>
      <h1 className="animate-element animate-delay-200 text-[clamp(1.8rem,3.6vw,2.4rem)] font-semibold leading-tight text-balance-tight">
        <span className="lp-text-bright">Welcome back</span>
      </h1>
      <p className="animate-element animate-delay-300 mt-2.5 text-[14.5px] text-white/45">
        Sign in to manage your models, chats and credits.
      </p>

      <form action={formAction} className="mt-9 space-y-5">
        {next && <input type="hidden" name="next" value={next} />}

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
          <PasswordField label="Password" name="password" />
        </div>

        <div className="animate-element animate-delay-600 flex items-center justify-between">
          <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-white/55">
            <input
              type="checkbox"
              name="remember"
              defaultChecked
              className="h-4 w-4 rounded border-white/20 bg-white/5 accent-white"
            />
            Keep me signed in
          </label>
          <Link
            href="/reset-password"
            className="text-[13px] font-medium text-white/70 underline-offset-4 transition-colors hover:text-white hover:underline"
          >
            Reset password
          </Link>
        </div>

        <div className="animate-element animate-delay-700">
          <SubmitButton>Sign In</SubmitButton>
        </div>
      </form>

      <div className="animate-element animate-delay-800 mt-7">
        <OrDivider />
      </div>

      <div className="animate-element animate-delay-900 mt-5">
        <GoogleButton label="Sign in with Google" />
      </div>

      <p className="animate-element animate-delay-1000 mt-8 text-center text-[13.5px] text-white/45">
        New to Telepipe?{" "}
        <Link
          href="/register"
          className="font-semibold text-white underline-offset-4 transition-colors hover:underline"
        >
          Create an account
        </Link>
      </p>
    </div>
  );
}

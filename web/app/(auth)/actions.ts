"use server";

import { redirect } from "next/navigation";

import { googleAuthEnabled, siteUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/** Stav formulárov pre `useActionState` — chyba alebo informačná hláška. */
export type AuthState = {
  error?: string;
  notice?: string;
  email?: string;
  /** register: účet vznikol, ale čaká na potvrdenie emailu */
  awaitingConfirmation?: boolean;
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const MIN_PASSWORD = 8;

/** Interné cesty — chránime sa pred open redirectom cez `?next=`. */
function safeNext(value: FormDataEntryValue | null): string {
  const next = typeof value === "string" ? value : "";
  // Spätné lomítko musí padnúť tiež: prehliadače normalizujú `\` na `/`, takže
  // `/\evil.com` alebo `\\evil.com` by inak prešlo ako protocol-relative URL.
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) {
    return "/app";
  }
  return next;
}

/** Supabase hlášky preložíme do zrozumiteľnej angličtiny. */
function friendlyError(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes("invalid login credentials")) {
    return "That email and password combination does not match an account.";
  }
  if (normalized.includes("email not confirmed")) {
    return "Please confirm your email address first — check your inbox for the link.";
  }
  if (normalized.includes("already registered") || normalized.includes("already been registered")) {
    return "An account with this email already exists. Try signing in instead.";
  }
  if (normalized.includes("rate limit") || normalized.includes("too many")) {
    return "Too many attempts. Please wait a minute and try again.";
  }
  if (normalized.includes("password should be")) {
    return `Password must be at least ${MIN_PASSWORD} characters long.`;
  }
  return message;
}

/* -------------------------------------------------------------------------- */
/*  Sign in                                                                    */
/* -------------------------------------------------------------------------- */

export async function signInAction(
  _prev: AuthState | undefined,
  formData: FormData,
): Promise<AuthState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const rememberMe = formData.get("remember") === "on";
  const next = safeNext(formData.get("next"));

  if (!EMAIL_RE.test(email)) {
    return { error: "Enter a valid email address.", email };
  }
  if (!password) {
    return { error: "Enter your password.", email };
  }

  const supabase = await createClient({ rememberMe });
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    return { error: friendlyError(error.message), email };
  }

  // redirect() hádže špeciálnu výnimku — nikdy nesmie byť v try/catch
  redirect(next);
}

/* -------------------------------------------------------------------------- */
/*  Sign up                                                                    */
/* -------------------------------------------------------------------------- */

export async function signUpAction(
  _prev: AuthState | undefined,
  formData: FormData,
): Promise<AuthState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm") ?? "");
  const accepted = formData.get("terms") === "on";

  if (!EMAIL_RE.test(email)) {
    return { error: "Enter a valid email address.", email };
  }
  if (password.length < MIN_PASSWORD) {
    return { error: `Password must be at least ${MIN_PASSWORD} characters long.`, email };
  }
  if (password !== confirm) {
    return { error: "Passwords do not match.", email };
  }
  if (!accepted) {
    return { error: "Please accept the terms to continue.", email };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: `${siteUrl()}/auth/callback?next=/app` },
  });

  if (error) {
    return { error: friendlyError(error.message), email };
  }

  // Supabase pri zapnutom email confirme vráti usera bez session. Ak už identity
  // pole je prázdne, email je v systéme — nehlásime to explicitne (user enumeration),
  // ukážeme rovnakú „check your email" obrazovku.
  if (!data.session) {
    return { awaitingConfirmation: true, email };
  }

  redirect("/app");
}

/* -------------------------------------------------------------------------- */
/*  Reset / update password                                                    */
/* -------------------------------------------------------------------------- */

export async function requestPasswordResetAction(
  _prev: AuthState | undefined,
  formData: FormData,
): Promise<AuthState> {
  const email = String(formData.get("email") ?? "").trim();

  if (!EMAIL_RE.test(email)) {
    return { error: "Enter a valid email address.", email };
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${siteUrl()}/auth/callback?next=/update-password`,
  });

  if (error) {
    return { error: friendlyError(error.message), email };
  }

  // Neprezrádzame či účet existuje — hláška je vždy rovnaká
  return {
    notice: "If an account exists for that address, a reset link is on its way.",
    email,
  };
}

export async function updatePasswordAction(
  _prev: AuthState | undefined,
  formData: FormData,
): Promise<AuthState> {
  const password = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm") ?? "");

  if (password.length < MIN_PASSWORD) {
    return { error: `Password must be at least ${MIN_PASSWORD} characters long.` };
  }
  if (password !== confirm) {
    return { error: "Passwords do not match." };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return {
      error: "This reset link has expired. Request a new one and try again.",
    };
  }

  const { error } = await supabase.auth.updateUser({ password });
  if (error) {
    return { error: friendlyError(error.message) };
  }

  redirect("/app");
}

/* -------------------------------------------------------------------------- */
/*  Google OAuth — kód je hotový, čaká na provider v Supabase                  */
/* -------------------------------------------------------------------------- */

export async function signInWithGoogleAction(): Promise<AuthState> {
  if (!googleAuthEnabled) {
    // Poistka na serveri — button je v UI aj tak disabled
    return { error: "Google sign-in is not available yet." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${siteUrl()}/auth/callback?next=/app`,
      queryParams: { access_type: "offline", prompt: "consent" },
    },
  });

  if (error) {
    return { error: friendlyError(error.message) };
  }
  if (data.url) {
    redirect(data.url);
  }
  return { error: "Could not start Google sign-in." };
}

/* -------------------------------------------------------------------------- */
/*  Sign out                                                                   */
/* -------------------------------------------------------------------------- */

export async function signOutAction() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}

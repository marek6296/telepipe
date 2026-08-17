"use server";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export type AccountState = { error?: string; notice?: string };

const MIN_PASSWORD = 8;

/**
 * Zmena hesla. Supabase `updateUser` staré heslo nepýta — pýtame ho my, inak
 * by stačil nezamknutý notebook na prevzatie účtu.
 */
export async function changePasswordAction(
  _prev: AccountState | undefined,
  formData: FormData,
): Promise<AccountState> {
  const current = String(formData.get("current") ?? "");
  const next = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm") ?? "");

  if (next.length < MIN_PASSWORD) {
    return { error: `Password must be at least ${MIN_PASSWORD} characters long.` };
  }
  if (next !== confirm) {
    return { error: "The new passwords do not match." };
  }
  if (next === current) {
    return { error: "That is your current password — pick a new one." };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user?.email) {
    return { error: "Your session expired. Sign in again and retry." };
  }

  const { error: reauth } = await supabase.auth.signInWithPassword({
    email: user.email,
    password: current,
  });
  if (reauth) {
    return { error: "Your current password is not right." };
  }

  const { error } = await supabase.auth.updateUser({ password: next });
  if (error) {
    return { error: error.message };
  }

  return { notice: "Password changed. Other devices stay signed in." };
}

/** Odhlásenie zo všetkých zariadení — zneplatní všetky refresh tokeny. */
export async function signOutEverywhereAction() {
  const supabase = await createClient();
  await supabase.auth.signOut({ scope: "global" });
  redirect("/login");
}

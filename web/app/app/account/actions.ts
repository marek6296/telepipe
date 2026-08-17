"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { encrypt } from "@/lib/crypto";
import { encryptionKey } from "@/lib/env";
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

/* -------------------------------------------------------------------------- */
/*  ElevenLabs — pripojenie účtu (migrácia 017)                                */
/* -------------------------------------------------------------------------- */

/**
 * Kľúč je tu ZÁMERNE na účte a nie na modelke: účet ElevenLabs je jeden,
 * faktúra je jedna. Kto má päť modeliek, pripojí ho raz a na kartách modeliek
 * si už len vyberá hlas.
 *
 * Cesta kľúča je rovnaká ako pri Telegram session a Fanvue tokenoch:
 * zašifruje sa tu (`ENCRYPTION_KEY`, server-only) a do DB ho pustí jedine
 * `set_account_eleven_key()`. Späť už nikdy nejde — von ide iba bit
 * „pripojené / nepripojené" z `has_account_eleven_key()`.
 */

/** Najkratší kľúč, aký ElevenLabs vydal (staré 32-znakové hexy). */
const MIN_ELEVEN_KEY = 24;

export async function connectElevenAction(
  _prev: AccountState | undefined,
  formData: FormData,
): Promise<AccountState> {
  const key = String(formData.get("eleven_key") ?? "").trim();

  if (key.length < MIN_ELEVEN_KEY) {
    return { error: "That does not look like an ElevenLabs API key." };
  }
  // Medzera vnútri je vždy zle skopírovaný text, nie kľúč. Bez tejto kontroly
  // by sa uložil, zašifroval, a ElevenLabs by ho odmietlo až pri prvom hlase.
  if (/\s/.test(key)) {
    return { error: "The key has a space in it — copy it again from ElevenLabs." };
  }

  const supabase = await createClient();
  const { error } = await supabase.rpc("set_account_eleven_key", {
    p_key_enc: await encrypt(key, encryptionKey()),
  });

  if (error) return { error: error.message };

  revalidatePath("/app/account");
  return { notice: "ElevenLabs connected. Pick a voice on each model's Voice tab." };
}

/** Odpojenie — kľúč sa z účtu vymaže, hlasy prestanú chodiť. */
export async function disconnectElevenAction(): Promise<AccountState> {
  const supabase = await createClient();
  const { error } = await supabase.rpc("clear_account_eleven_key");

  if (error) return { error: error.message };

  revalidatePath("/app/account");
  return { notice: "ElevenLabs disconnected." };
}

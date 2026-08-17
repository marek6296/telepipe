"use server";

import { revalidatePath } from "next/cache";

import { encrypt } from "@/lib/crypto";
import { encryptionKey } from "@/lib/env";
import { getModel, requireUser } from "@/lib/models";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { LOGIN_JOB_COLUMNS, type LoginJob } from "@/lib/telegram";

/**
 * Server actions Telegram wizardu.
 *
 * Next.js nevie MTProto, takže prihlásenie beží cez frontu `tg_login_jobs`,
 * ktorú spracúva worker (`worker/src/login_jobs.py`). Tu len šifrujeme
 * tajomstvá tým istým `ENCRYPTION_KEY` a posúvame fázu:
 *
 *   my → phase send_code            worker → code_sent | error
 *   my → code_enc + verify_code     worker → done | need_password | code_sent(invalid_code)
 *   my → password_enc + verify_password  worker → done | need_password(invalid_password)
 *
 * ENCRYPTION_KEY ani service kľúč sa nikdy nesmú dostať do client bundlu —
 * tento súbor je "use server", takže sa importuje výhradne na serveri.
 */

export type WizardResult = {
  error?: string;
  ok?: boolean;
  jobId?: number;
  detail?: string;
};

const PHONE_RE = /^\+[1-9]\d{6,14}$/;
const API_HASH_RE = /^[a-fA-F0-9]{32}$/;
const CODE_RE = /^\d{4,8}$/;
const BOT_TOKEN_RE = /^\d{6,12}:[A-Za-z0-9_-]{30,}$/;

/** Fázy, v ktorých job ešte žije — pri novom pokuse ich treba zavrieť. */
const LIVE_PHASES = [
  "send_code",
  "code_sent",
  "verify_code",
  "need_password",
  "verify_password",
];

/** Overí, že modelka patrí prihlásenému (RLS by cudziu ani nevrátila). */
async function ownedModel(modelId: string) {
  const model = await getModel(modelId);
  if (!model) return null;
  return model;
}

/* -------------------------------------------------------------------------- */
/*  1–2. api_id + api_hash + telefón → nový job                                */
/* -------------------------------------------------------------------------- */

export async function startTelegramLoginAction(input: {
  modelId: string;
  apiId: string;
  apiHash: string;
  phone: string;
}): Promise<WizardResult> {
  const user = await requireUser();
  const model = await ownedModel(input.modelId);
  if (!model) return { error: "Model not found." };

  const apiId = Number.parseInt(input.apiId.trim(), 10);
  if (!Number.isInteger(apiId) || apiId <= 0 || apiId > 2_147_483_647) {
    return { error: "api_id must be the number you got from my.telegram.org." };
  }

  const apiHash = input.apiHash.trim();
  if (!API_HASH_RE.test(apiHash)) {
    return { error: "api_hash is a 32-character string of letters and digits." };
  }

  const phone = input.phone.replace(/[\s()-]/g, "");
  if (!PHONE_RE.test(phone)) {
    return { error: "Enter the phone number in international format, e.g. +421901234567." };
  }

  const supabase = await createClient();

  // Staré rozrobené pokusy zavrieme, nech worker nespracúva dva naraz.
  await supabase
    .from("tg_login_jobs")
    .update({ phase: "error", updated_at: new Date().toISOString() })
    .eq("model_id", model.id)
    .in("phase", LIVE_PHASES);

  const { data, error } = await supabase
    .from("tg_login_jobs")
    .insert({
      model_id: model.id,
      account_id: user.id,
      phase: "send_code",
      phone,
      api_id: apiId,
      api_hash_enc: await encrypt(apiHash, encryptionKey()),
    })
    .select("id")
    .single();

  if (error || !data) {
    // DB throttle (migrácia 008) bráni zaplaveniu Telegram SMS kódmi a DoS-u
    // zdieľaného workera — hlášku prekladáme do zrozumiteľnej angličtiny.
    if (error?.message.includes("rate_limit")) {
      return { error: "Too many attempts. Please wait a few minutes and try again." };
    }
    return { error: error?.message ?? "Could not start the login. Please try again." };
  }

  // api_id si držíme pri modelke, nech ho pri reconnecte netreba prepisovať.
  // (`tg_api_hash` plní worker po úspešnom prihlásení — klient naň nemá grant.)
  if (model.tg_api_id !== apiId) {
    await supabase
      .from("models")
      .update({ tg_api_id: apiId, updated_at: new Date().toISOString() })
      .eq("id", model.id);
  }

  return { ok: true, jobId: data.id as number };
}

/* -------------------------------------------------------------------------- */
/*  3. SMS kód a 2FA heslo                                                     */
/* -------------------------------------------------------------------------- */

export async function submitLoginCodeAction(
  jobId: number,
  code: string,
): Promise<WizardResult> {
  const clean = code.replace(/\D/g, "");
  if (!CODE_RE.test(clean)) {
    return { error: "The code from Telegram is 5 digits." };
  }

  const supabase = await createClient();
  const { error } = await supabase
    .from("tg_login_jobs")
    .update({
      code_enc: await encrypt(clean, encryptionKey()),
      phase: "verify_code",
      updated_at: new Date().toISOString(),
    })
    .eq("id", jobId);

  if (error) return { error: error.message };
  return { ok: true };
}

export async function submitLoginPasswordAction(
  jobId: number,
  password: string,
): Promise<WizardResult> {
  if (!password) return { error: "Enter your Telegram two-step password." };

  const supabase = await createClient();
  const { error } = await supabase
    .from("tg_login_jobs")
    .update({
      password_enc: await encrypt(password, encryptionKey()),
      phase: "verify_password",
      updated_at: new Date().toISOString(),
    })
    .eq("id", jobId);

  if (error) return { error: error.message };
  return { ok: true };
}

/** „Start over" — rozrobený job zavrieme, wizard sa vráti na prvý krok. */
export async function cancelLoginJobAction(jobId: number): Promise<WizardResult> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("tg_login_jobs")
    .update({ phase: "error", updated_at: new Date().toISOString() })
    .eq("id", jobId);

  if (error) return { error: error.message };
  return { ok: true };
}

/* -------------------------------------------------------------------------- */
/*  Polling                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Stav jobu pre polling (každé 2 s, rovnako často ako beží worker).
 * Vracia len stĺpce, na ktoré má klient grant — `*_enc` von nikdy nejdú.
 */
export async function pollLoginJobAction(
  modelId: string,
): Promise<{ job: LoginJob | null; connected: boolean }> {
  const supabase = await createClient();

  const [latest, done] = await Promise.all([
    supabase
      .from("tg_login_jobs")
      .select(LOGIN_JOB_COLUMNS)
      .eq("model_id", modelId)
      .order("id", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("tg_login_jobs")
      .select("id")
      .eq("model_id", modelId)
      .eq("phase", "done")
      .limit(1)
      .maybeSingle(),
  ]);

  return {
    job: (latest.data as LoginJob | null) ?? null,
    connected: Boolean(done.data),
  };
}

/* -------------------------------------------------------------------------- */
/*  4. Kontrolný bot + owner chat id                                           */
/* -------------------------------------------------------------------------- */

export async function saveControlBotAction(input: {
  modelId: string;
  token: string;
  ownerChatId: string;
}): Promise<WizardResult> {
  const user = await requireUser();
  const model = await ownedModel(input.modelId);
  if (!model) return { error: "Model not found." };

  const token = input.token.trim();

  // Prázdny token znamená „nechaj ten, čo tam je, mením len chat id".
  // Bez tejto vetvy sa owner_chat_id nedal opraviť inak než opätovným
  // vylepením tokenu — a ten sa do políčka nikdy nepredvyplní (je šifrovaný,
  // von už nikdy nejde), takže oprava jedného čísla znamenala výlet do
  // @BotFathera po token, ktorý sa vôbec nemenil.
  const keepExistingToken = token === "";
  if (keepExistingToken && !(await controlBotConfigured(model.id))) {
    return { error: "Paste the bot token from @BotFather first." };
  }
  if (!keepExistingToken && !BOT_TOKEN_RE.test(token)) {
    return {
      error: "That does not look like a bot token. It looks like 123456789:AA-long-string.",
    };
  }

  const ownerChatId = Number.parseInt(input.ownerChatId.trim(), 10);
  if (!Number.isSafeInteger(ownerChatId) || ownerChatId === 0) {
    return { error: "Chat ID is the number @userinfobot replies with." };
  }

  // Overenie u Telegramu — lepšie zistiť preklep tu než mlčaním bota.
  const check: { username?: string; error?: string } = keepExistingToken
    ? {}
    : await verifyBotToken(token);
  if (check.error) return { error: check.error };

  const supabase = await createClient();
  const { error: ownerError } = await supabase
    .from("models")
    .update({ owner_chat_id: ownerChatId, updated_at: new Date().toISOString() })
    .eq("id", model.id);
  if (ownerError) return { error: ownerError.message };

  if (!keepExistingToken) {
    // `control_bot_token_enc` klient zapísať nevie (žiadny column grant) — ide to
    // service kľúčom, ktorý RLS obchádza, preto to `eq("account_id")` tu musí byť.
    const admin = createServiceClient();
    const { error } = await admin
      .from("models")
      .update({
        control_bot_token_enc: await encrypt(token, encryptionKey()),
        updated_at: new Date().toISOString(),
      })
      .eq("id", model.id)
      .eq("account_id", user.id);

    if (error) return { error: error.message };
  }

  revalidatePath(`/app/m/${model.id}/telegram`);
  return { ok: true, detail: check.username ? `@${check.username}` : undefined };
}

/** Telegram Bot API `getMe` — overí, že token žije. */
async function verifyBotToken(token: string): Promise<{ username?: string; error?: string }> {
  try {
    const response = await fetch(`https://api.telegram.org/bot${token}/getMe`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    const body = (await response.json()) as {
      ok?: boolean;
      description?: string;
      result?: { username?: string };
    };
    if (!body.ok) {
      return {
        error:
          body.description === "Unauthorized"
            ? "Telegram rejected that token. Copy it again from @BotFather."
            : `Telegram said: ${body.description ?? "the token is not valid"}.`,
      };
    }
    return { username: body.result?.username };
  } catch {
    // Sieť môže vypadnúť aj keď je token v poriadku — nech to klienta neblokuje.
    return {};
  }
}

/** Má modelka uložený token? Stĺpec je šifrovaný a klient naň nevidí. */
export async function controlBotConfigured(modelId: string): Promise<boolean> {
  const user = await requireUser();
  const model = await ownedModel(modelId);
  if (!model) return false;

  const admin = createServiceClient();
  const { data } = await admin
    .from("models")
    .select("control_bot_token_enc")
    .eq("id", model.id)
    .eq("account_id", user.id)
    .maybeSingle();

  return Boolean((data?.control_bot_token_enc as string | undefined)?.length);
}

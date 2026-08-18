"use server";

import { revalidatePath } from "next/cache";

import { decrypt, encrypt } from "@/lib/crypto";
import { encryptionKey } from "@/lib/env";
import { getModel, requireUser } from "@/lib/models";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { LOGIN_JOB_COLUMNS, type LoginJob } from "@/lib/telegram";
import {
  checkApiHash,
  checkApiId,
  checkBotToken,
  checkChatId,
  checkPhone,
  normalizePhone,
} from "@/lib/telegram-setup";

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

/**
 * `field` hovorí wizardu, KDE chybu vykresliť. Bez neho sa hláška o `api_id`
 * ukázala pod políčkom s telefónom — o dva kroky ďalej, než chyba vznikla.
 * Wizard z toho zároveň vie, či má ponúknuť odkaz „Back to API keys".
 */
export type WizardField = "api_id" | "api_hash" | "phone" | "code" | "password" | "token"
  | "chat_id";

export type WizardResult = {
  error?: string;
  field?: WizardField;
  ok?: boolean;
  jobId?: number;
  detail?: string;
};

const CODE_RE = /^\d{4,8}$/;

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
/*  1. api_id + api_hash → do DB hneď, nie až s prihlásením                    */
/* -------------------------------------------------------------------------- */

/**
 * Overí a ULOŽÍ kľúče v okamihu, keď klient opúšťa prvý krok.
 *
 * PREČO VÔBEC. Prvý krok doteraz posúval len lokálny `useState`. Stepper preto
 * svietil zeleným „API keys ✓", hoci v `models` bolo `tg_api_id NULL` a prázdny
 * hash — kľúče sa zapisovali až pri zakladaní login jobu. Zelená fajka teda
 * tvrdila niečo, čo nebola pravda, a po refreshi stránky sa krok vrátil na
 * začiatok. Odteraz platí opak: fajka číta stav z databázy, takže sa nemá ako
 * rozísť s realitou.
 *
 * `tg_api_id` klient zapisuje sám (má na stĺpec update grant), `tg_api_hash`
 * NIE — grant naň nemá (overené na produkčnej DB). Ide teda service kľúčom, a
 * keďže ten obchádza RLS, je tu `eq("account_id", user.id)` povinné. Rovnaký
 * postup ako pri `control_bot_token_enc` nižšie.
 */
export async function saveApiKeysAction(input: {
  modelId: string;
  apiId: string;
  apiHash: string;
}): Promise<WizardResult> {
  const user = await requireUser();
  const model = await ownedModel(input.modelId);
  if (!model) return { error: "Model not found." };

  const apiId = input.apiId.trim();
  const apiHash = input.apiHash.trim();

  if (!apiId) return { error: "Fill in api_id from my.telegram.org.", field: "api_id" };
  const idCheck = checkApiId(apiId);
  if (!idCheck.ok) return { error: idCheck.message, field: "api_id" };

  if (!apiHash) return { error: "Fill in api_hash from my.telegram.org.", field: "api_hash" };
  const hashCheck = checkApiHash(apiHash);
  if (!hashCheck.ok) return { error: hashCheck.message, field: "api_hash" };

  const supabase = await createClient();
  const { error: idError } = await supabase
    .from("models")
    .update({ tg_api_id: Number(apiId), updated_at: new Date().toISOString() })
    .eq("id", model.id);
  if (idError) return { error: idError.message, field: "api_id" };

  const admin = createServiceClient();
  const { error: hashError } = await admin
    .from("models")
    .update({ tg_api_hash: apiHash.toLowerCase(), updated_at: new Date().toISOString() })
    .eq("id", model.id)
    .eq("account_id", user.id);
  if (hashError) return { error: hashError.message, field: "api_hash" };

  revalidatePath(`/app/m/${model.id}/telegram`, "layout");
  return { ok: true };
}

/* -------------------------------------------------------------------------- */
/*  2. api_id + api_hash + telefón → nový job                                  */
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

  // Server ostáva autoritou: klient tie isté kontroly robí pri opustení
  // políčka, ale spoľahnúť sa na ne nemožno. `field` posiela hlášku späť k
  // políčku, ktoré ju spôsobilo — aj keď je o krok späť.
  const rawApiId = input.apiId.trim();
  if (!rawApiId) return { error: "Fill in api_id from my.telegram.org.", field: "api_id" };
  const idCheck = checkApiId(rawApiId);
  if (!idCheck.ok) return { error: idCheck.message, field: "api_id" };
  const apiId = Number(rawApiId);

  const apiHash = input.apiHash.trim();
  if (!apiHash) return { error: "Fill in api_hash from my.telegram.org.", field: "api_hash" };
  const hashCheck = checkApiHash(apiHash);
  if (!hashCheck.ok) return { error: hashCheck.message, field: "api_hash" };

  const phone = normalizePhone(input.phone);
  if (!phone) return { error: "Enter her phone number.", field: "phone" };
  const phoneCheck = checkPhone(phone);
  if (!phoneCheck.ok) return { error: phoneCheck.message, field: "phone" };

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
      return {
        error: "Too many attempts. Please wait a few minutes and try again.",
        field: "phone",
      };
    }
    return {
      error: error?.message ?? "Could not start the login. Please try again.",
      field: "phone",
    };
  }

  // Poistka pre klienta, ktorý sa na krok 1 vrátil a hodnotu prepísal: kľúče
  // ukladá `saveApiKeysAction`, ale nech sa stepper a DB nerozídu ani vtedy,
  // keď sa sem niekto dostane inou cestou.
  if (model.tg_api_id !== apiId || model.tg_api_hash !== apiHash.toLowerCase()) {
    await saveApiKeysAction({ modelId: model.id, apiId: rawApiId, apiHash });
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
    return { error: "The code from Telegram is 5 digits.", field: "code" };
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
  if (!password) return { error: "Enter her Telegram two-step password.", field: "password" };

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
  /** Nepovinné — bežná cesta je párovanie kódom, toto je pokročilá záloha. */
  ownerChatId?: string;
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
    return { error: "Paste the bot token from @BotFather first.", field: "token" };
  }
  if (!keepExistingToken) {
    const tokenCheck = checkBotToken(token);
    if (!tokenCheck.ok) return { error: tokenCheck.message, field: "token" };
  }

  // Chat id je odteraz NEPOVINNÉ: bežná cesta je párovací kód, ktorý si číslo
  // zapíše sám z chatu, ktorý kód poslal. Ručné prepisovanie ostáva ako
  // pokročilá záloha (Marek chce oboje) — keď je políčko prázdne, hodnota
  // v DB sa nechá tak, nech uloženie nového tokenu nerozpáruje bežiaceho bota.
  const rawChatId = (input.ownerChatId ?? "").trim();
  const chatCheck = checkChatId(rawChatId);
  if (!chatCheck.ok) return { error: chatCheck.message, field: "chat_id" };
  const ownerChatId = rawChatId ? Number(rawChatId) : null;

  // Overenie u Telegramu — lepšie zistiť preklep tu než mlčaním bota.
  const check: { username?: string; error?: string } = keepExistingToken
    ? {}
    : await verifyBotToken(token);
  if (check.error) return { error: check.error, field: "token" };

  const supabase = await createClient();
  if (ownerChatId !== null) {
    const { error: ownerError } = await supabase
      .from("models")
      .update({ owner_chat_id: ownerChatId, updated_at: new Date().toISOString() })
      .eq("id", model.id);
    if (ownerError) return { error: ownerError.message, field: "chat_id" };
  }

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

    if (error) return { error: error.message, field: "token" };

    await restartTenantIfRunning(model.id, model.status);
  }

  // `layout` = celý podstrom `/telegram/*`: token sa ukladá v Settings aj v
  // kroku sprievodcu a stav „bot je nastavený" číta oboje.
  revalidatePath(`/app/m/${model.id}/telegram`, "layout");
  return { ok: true, detail: check.username ? `@${check.username}` : undefined };
}

/**
 * Nový token bota u BEŽIACEJ modelky → nech si ju worker zoberie odznova.
 *
 * `TenantConfig` sa v `main.py` skladá RAZ, pri claime, a `runner.py` volá
 * `bot_client.start(bot_token=cfg.control_bot_token)` tiež raz na začiatku
 * behu. Token pridaný AŽ POTOM (klient aktivoval modelku a bota si dorobil o
 * hodinu neskôr, čo je presne cesta, ktorú „Skip for now" ponúka) by teda ležal
 * v databáze bez účinku až do najbližšieho reštartu repliky.
 *
 * Najlacnejšia správna oprava je pustiť lease: `release_model` vynuluje
 * `claimed_by`, do 30 s (`claim_interval_s`) ho `heartbeat_models` prestane
 * vracať, pool tenanta odstaví (`_fence`) a hneď v ďalšom kole si ho doklaimuje
 * s čerstvým configom. Telethon session je uložená v `tg_session_enc`, takže sa
 * NIČ neprihlasuje nanovo — modelka je späť online v tom istom čase, ktorý
 * sľubuje aktivácia. Robí sa to servisným kľúčom, lebo `release_model` je
 * grantované len `service_role`.
 *
 * PÁROVANIE toto nepotrebuje: kód prijíma bežiaci bot a `owner_chat_id` si mení
 * priamo v configu, ktorý drží v ruke (viď `control_bot.py`). Reštart je nutný
 * len pre token, ktorý sa číta pri štarte.
 */
async function restartTenantIfRunning(modelId: string, status: string): Promise<void> {
  if (status !== "active" && status !== "paused") return;
  try {
    await createServiceClient().rpc("release_model", { p_model: modelId });
  } catch {
    // Lease sa vždy dá pustiť aj reštartom repliky — nech to neblokuje uloženie.
  }
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

/* -------------------------------------------------------------------------- */
/*  5. Párovanie kontrolného bota kódom (migrácia 020)                         */
/* -------------------------------------------------------------------------- */

/**
 * PROTOKOL. Dashboard si vypýta jednorazový kód → klient ho pošle svojmu botovi
 * → bot (worker, service kľúč) kód spotrebuje cez RPC `pair_control_bot` a
 * zapíše `models.owner_chat_id` z chatu, ktorý kód poslal → dashboard to uvidí
 * pri najbližšom pollingu.
 *
 * Nahrádza to opisovanie chat id z @userinfobota. Preklep v tom čísle sa totiž
 * nedal odhaliť: `control_bot.py` gatuje každý handler na
 * `chat_id == cfg.owner_chat_id`, takže pri zlom čísle bot mlčal aj na `/start`
 * a klient nemal ako zistiť, či je chyba v tokene, v čísle alebo v produkte.
 *
 * Kód sem nikdy nepíšeme my — generuje ho databáza (before-insert trigger),
 * klient má insert grant len na `model_id`/`account_id`.
 */
export type PairingCode = { code: string; expiresAt: string };

export type ControlBotState = {
  /** Je uložený token? Bez neho nemá kód komu poslať. */
  hasToken: boolean;
  /** Spárované = `models.owner_chat_id` nie je prázdne. */
  paired: boolean;
  ownerChatId: number | null;
  /** `@meno` majiteľa, ak sa dá zistiť; inak sa ukáže samotné chat id. */
  ownerLabel: string | null;
  /** Živý (nepoužitý, nevypršaný) kód, ak nejaký je. */
  pending: PairingCode | null;
};

/** Živý kód modelky — nepoužitý a ešte nevypršaný. */
async function livePairingCode(modelId: string): Promise<PairingCode | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("control_bot_links")
    .select("code, expires_at")
    .eq("model_id", modelId)
    .is("used_at", null)
    .gt("expires_at", new Date().toISOString())
    .order("id", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (!data) return null;
  return { code: data.code as string, expiresAt: data.expires_at as string };
}

export async function createPairingCodeAction(
  modelId: string,
): Promise<{ code?: PairingCode; error?: string }> {
  const user = await requireUser();
  const model = await ownedModel(modelId);
  if (!model) return { error: "Model not found." };

  if (!(await controlBotConfigured(model.id))) {
    return { error: "Save the bot token first — the code has to be sent to your own bot." };
  }

  const supabase = await createClient();

  // Naraz smie žiť jeden kód na modelku (partial unique index v 020). Staré
  // nepoužité riadky preto najprv zmažeme — inak by druhé kliknutie na
  // „Generate" spadlo na unique violation. Spárované riadky sa nemažú (delete
  // policy ich nepustí): sú záznamom o tom, ktorý chat sa kedy pripojil.
  await supabase
    .from("control_bot_links")
    .delete()
    .eq("model_id", model.id)
    .is("used_at", null);

  const { error } = await supabase
    .from("control_bot_links")
    .insert({ model_id: model.id, account_id: user.id });
  if (error) return { error: error.message };

  // Insert nevracia `code` (klient nemá `returning` na stĺpec, ktorý nezapisuje),
  // preto sa naň pýtame samostatným selectom.
  const code = await livePairingCode(model.id);
  if (!code) return { error: "Could not create a pairing code. Try again." };
  return { code };
}

export async function pollControlBotAction(modelId: string): Promise<ControlBotState> {
  const model = await ownedModel(modelId);
  if (!model) {
    return { hasToken: false, paired: false, ownerChatId: null, ownerLabel: null, pending: null };
  }

  const [hasToken, pending] = await Promise.all([
    controlBotConfigured(model.id),
    livePairingCode(model.id),
  ]);

  const ownerChatId = model.owner_chat_id ?? null;
  return {
    hasToken,
    paired: Boolean(ownerChatId),
    ownerChatId,
    ownerLabel: ownerChatId ? await ownerLabel(model.id, ownerChatId) : null,
    pending,
  };
}

/**
 * `@meno` chatu, do ktorého bot píše. Je to len ozdoba potvrdenia — keď sa
 * nedá zistiť (bot padol, sieť, chat bez username), vráti sa `null` a UI ukáže
 * číslo. Nikdy to nesmie zhodiť pollovanie.
 */
async function ownerLabel(modelId: string, chatId: number): Promise<string | null> {
  try {
    const admin = createServiceClient();
    const { data } = await admin
      .from("models")
      .select("control_bot_token_enc")
      .eq("id", modelId)
      .maybeSingle();

    const enc = data?.control_bot_token_enc as string | undefined;
    if (!enc) return null;

    const token = await decrypt(enc, encryptionKey());
    const response = await fetch(
      `https://api.telegram.org/bot${token}/getChat?chat_id=${chatId}`,
      { cache: "no-store", signal: AbortSignal.timeout(6000) },
    );
    const body = (await response.json()) as {
      ok?: boolean;
      result?: { username?: string; first_name?: string };
    };
    if (!body.ok) return null;
    const { username, first_name: firstName } = body.result ?? {};
    return username ? `@${username}` : (firstName ?? null);
  } catch {
    return null;
  }
}

/** Odpojenie — bot ostáva uložený, len už nemá majiteľa a dá sa spárovať znova. */
export async function unlinkControlBotAction(modelId: string): Promise<WizardResult> {
  const model = await ownedModel(modelId);
  if (!model) return { error: "Model not found." };

  const supabase = await createClient();
  const { error } = await supabase
    .from("models")
    .update({ owner_chat_id: null, updated_at: new Date().toISOString() })
    .eq("id", model.id);
  if (error) return { error: error.message };

  // Bežiaci bot si `owner_chat_id` drží v pamäti (viď `restartTenantIfRunning`),
  // takže bez reštartu by starému chatu ďalej odpovedal.
  await restartTenantIfRunning(model.id, model.status);

  revalidatePath(`/app/m/${model.id}/telegram`, "layout");
  return { ok: true };
}

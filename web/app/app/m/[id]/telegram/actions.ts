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

/**
 * Stav DVOCH nezávislých vecí, nie jednej.
 *
 * `hasToken` = „bot existuje a jeho token je uložený". `paired` = „ten bot vie,
 * komu má písať". Sú to dva kroky a dá sa mať prvý bez druhého (uložený token
 * bez spárovaného chatu je bot, ktorý beží a mlčí). UI ich preto ukazuje ako dva
 * bloky s vlastným stavom — kým sa po spárovaní všetko zbalilo do jedného
 * „Connected as X", nedalo sa prečítať, čo z toho je čo, ani to druhé zmeniť bez
 * rozbitia prvého.
 */
export type ControlBotState = {
  /** Je uložený token? Bez neho nemá kód komu poslať. */
  hasToken: boolean;
  /** `@meno` samotného bota (z `getMe`), ak sa dá zistiť. */
  botLabel: string | null;
  /** Spárované = `models.owner_chat_id` nie je prázdne. */
  paired: boolean;
  ownerChatId: number | null;
  /** `@meno` majiteľa, ak sa dá zistiť; inak sa ukáže samotné chat id. */
  ownerLabel: string | null;
  /** `models.owner_as_client` — odpisuje modelka aj do majiteľovho chatu? */
  ownerAsClient: boolean;
  /** Živý (nepoužitý, nevypršaný) kód, ak nejaký je. */
  pending: PairingCode | null;
};

const EMPTY_CONTROL_BOT: ControlBotState = {
  hasToken: false,
  botLabel: null,
  paired: false,
  ownerChatId: null,
  ownerLabel: null,
  ownerAsClient: false,
  pending: null,
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
  if (!model) return EMPTY_CONTROL_BOT;

  const ownerChatId = model.owner_chat_id ?? null;
  const [labels, pending] = await Promise.all([
    telegramLabels(model.id, ownerChatId),
    livePairingCode(model.id),
  ]);

  return {
    hasToken: labels.hasToken,
    botLabel: labels.bot,
    paired: Boolean(ownerChatId),
    ownerChatId,
    ownerLabel: labels.owner,
    ownerAsClient: Boolean(model.owner_as_client),
    pending,
  };
}

/**
 * Mená bota a majiteľovho chatu — jedno dešifrovanie tokenu, dva dotazy naraz.
 *
 * Sú to len ozdoby potvrdenia: keď sa nedajú zistiť (bot padol, sieť, chat bez
 * username), vrátia sa `null` a UI ukáže samotné číslo. Nikdy to nesmie zhodiť
 * pollovanie — preto je celé telo v `try`.
 *
 * `hasToken` sa berie odtiaľto, a nie zo samostatného dotazu: je to ten istý
 * riadok a ten istý stĺpec, takže dva dotazy by len znamenali dve pravdy.
 */
async function telegramLabels(
  modelId: string,
  ownerChatId: number | null,
): Promise<{ hasToken: boolean; bot: string | null; owner: string | null }> {
  const user = await requireUser();
  const admin = createServiceClient();
  const { data } = await admin
    .from("models")
    .select("control_bot_token_enc")
    .eq("id", modelId)
    .eq("account_id", user.id)
    .maybeSingle();

  const enc = (data?.control_bot_token_enc as string | undefined) ?? "";
  if (!enc) return { hasToken: false, bot: null, owner: null };

  try {
    const token = await decrypt(enc, encryptionKey());
    const [me, chat] = await Promise.all([
      telegramCall(token, "getMe"),
      ownerChatId ? telegramCall(token, `getChat?chat_id=${ownerChatId}`) : null,
    ]);
    return {
      hasToken: true,
      bot: me?.username ? `@${me.username}` : null,
      owner: chat ? (chat.username ? `@${chat.username}` : (chat.first_name ?? null)) : null,
    };
  } catch {
    // Token je uložený aj keď sa Telegram nedovolá — to je stav, nie chyba.
    return { hasToken: true, bot: null, owner: null };
  }
}

async function telegramCall(
  token: string,
  method: string,
): Promise<{ username?: string; first_name?: string } | null> {
  try {
    const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    const body = (await response.json()) as {
      ok?: boolean;
      result?: { username?: string; first_name?: string };
    };
    return body.ok ? (body.result ?? null) : null;
  } catch {
    return null;
  }
}

/**
 * Odpojenie SÚKROMNÉHO TELEGRAMU (blok 3), nie bota.
 *
 * Token ostáva uložený, zmizne len `owner_chat_id` — bot ďalej existuje, len
 * nemá komu písať a dá sa spárovať z iného účtu. Zmazať samotného bota vie
 * `removeControlBotAction` nižšie; sú to zámerne dve tlačidlá, lebo je to
 * zámerne dvoje.
 */
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

/**
 * Zmazanie BOTA (blok 2). Berie so sebou aj spárovanie — bot bez tokenu nemá
 * ako doručiť notifikáciu, takže ponechaný `owner_chat_id` by tvrdil niečo, čo
 * už neplatí.
 *
 * Ide to service kľúčom (na `control_bot_token_enc` klient grant nemá), a preto
 * je tu `eq("account_id")` povinné — service kľúč RLS obchádza. Oba stĺpce sa
 * menia jedným príkazom, nech nemôže vzniknúť polovičný stav.
 */
export async function removeControlBotAction(modelId: string): Promise<WizardResult> {
  const user = await requireUser();
  const model = await ownedModel(modelId);
  if (!model) return { error: "Model not found." };

  const admin = createServiceClient();
  const { error } = await admin
    .from("models")
    .update({
      control_bot_token_enc: null,
      owner_chat_id: null,
      updated_at: new Date().toISOString(),
    })
    .eq("id", model.id)
    .eq("account_id", user.id);
  if (error) return { error: error.message };

  await restartTenantIfRunning(model.id, model.status);
  revalidatePath(`/app/m/${model.id}/telegram`, "layout");
  return { ok: true };
}

/* -------------------------------------------------------------------------- */
/*  6. „Odpisuje aj mne" — models.owner_as_client (migrácia 023)               */
/* -------------------------------------------------------------------------- */

/**
 * Prepínač, ktorý z majiteľovho chatu spraví bežný fanúšikovský chat.
 *
 * ČO SA ZAPNE. `userbot.py:198` inak správu od majiteľa preskočí (je to
 * ovládací kanál, nie fanúšik). So zapnutým `owner_as_client` sa spracuje ako
 * ktorákoľvek iná — modelka odpisuje aj tebe, a `userbot.py:319` ten chat
 * označí za testovací. Až vtedy má „vymazať testovací chat" čo mazať.
 *
 * PREČO REŠTART. `TenantConfig` sa skladá RAZ, pri claime (`main.py`, krok 3),
 * a `owner_as_client` sa z neho číta priamo (`self._cfg.owner_as_client`) —
 * žiadny TTL, žiadne osvieženie. Prepnutie pod bežiacim runnerom by teda ležalo
 * v databáze bez účinku až do najbližšieho reštartu repliky. Preto to isté, čo
 * robí zmena tokenu: pustiť lease a nechať sa doklaimovať s čerstvým configom.
 * Telethon session sa nemení, takže sa nikto nanovo neprihlasuje.
 *
 * PREČO LEN SO SPÁROVANÝM SÚKROMNÝM TELEGRAMOM. Bez `owner_chat_id` prepínač
 * nemá čo označiť — `is_owner` sa porovnáva práve s ním. Zapnúť ho „dopredu" by
 * znamenalo zaškrtnuté políčko bez akéhokoľvek účinku.
 */
export async function setOwnerAsClientAction(
  modelId: string,
  value: boolean,
): Promise<WizardResult> {
  const model = await ownedModel(modelId);
  if (!model) return { error: "Model not found." };
  if (!model.owner_chat_id) {
    return { error: "Pair your private Telegram first — without it there is no chat to switch." };
  }

  const supabase = await createClient();
  const { error } = await supabase
    .from("models")
    .update({ owner_as_client: value, updated_at: new Date().toISOString() })
    .eq("id", model.id);
  if (error) return { error: error.message };

  await restartTenantIfRunning(model.id, model.status);
  revalidatePath(`/app/m/${model.id}/telegram`, "layout");
  return { ok: true };
}

/* -------------------------------------------------------------------------- */
/*  6b. Kontaktový filter — models.skip_contacts / contact_exceptions (023b)   */
/* -------------------------------------------------------------------------- */

/**
 * „Smie písať ľuďom, ktorých má v kontaktoch?"
 *
 * PREČO TO TU JE. Marekovmu kamarátovi (chat 6977754097) Simona neodpovedala,
 * kým Marekovi odpovedala. `userbot.py:203-210` preskočí odosielateľa, ktorý je
 * v kontaktoch účtu — a majiteľ ten filter obchádza, takže to vyzeralo, že
 * produkt funguje jednému a druhému nie. Obe hodnoty pritom žili v PROCESNOM
 * prostredí repliky, teda jedna pre všetkých tenantov; na Railway neboli
 * nastavené vôbec. Od migrácie 023b sú to stĺpce modelky a toto je jediné
 * miesto, kde ich klient mení.
 *
 * REŠTART. Rovnako ako `owner_as_client`: `TenantConfig` sa skladá pri claime a
 * `userbot` číta `self._cfg.skip_contacts` priamo, takže bez pustenia lease by
 * zmena ležala v databáze bez účinku. `restartTenantIfRunning` to spraví do 30 s
 * bez opätovného prihlasovania.
 */
export type ContactRule = { skipContacts: boolean; exceptions: number[] };

export async function setContactRuleAction(
  modelId: string,
  rule: ContactRule,
): Promise<WizardResult> {
  const model = await ownedModel(modelId);
  if (!model) return { error: "Model not found." };

  // Duplicity a nuly von — `models_contact_exceptions_check` nulu odmieta a
  // dvakrát to isté id nemá význam.
  const seen = new Set<number>();
  for (const raw of rule.exceptions) {
    if (!Number.isSafeInteger(raw) || raw === 0) {
      return { error: "A chat ID is a whole number, the one @userinfobot replies with.", field: "chat_id" };
    }
    seen.add(raw);
  }

  const supabase = await createClient();
  const { error } = await supabase
    .from("models")
    .update({
      skip_contacts: rule.skipContacts,
      contact_exceptions: [...seen],
      updated_at: new Date().toISOString(),
    })
    .eq("id", model.id);
  if (error) return { error: error.message, field: "chat_id" };

  await restartTenantIfRunning(model.id, model.status);
  revalidatePath(`/app/m/${model.id}/telegram`, "layout");
  return { ok: true };
}

/* -------------------------------------------------------------------------- */
/*  7. Vymazanie testovacieho chatu                                            */
/* -------------------------------------------------------------------------- */

/**
 * To isté, čo robí „🧹 Vymazať pamäť tejto konverzácie" v menu kontrolného bota
 * (`control_bot.py::_wipe` → `db.wipe_conversation`), len z dashboardu.
 *
 * BEZPEČNOSŤ. Akcia NEBERIE `tg_id` — berie len `modelId`. Číslo chatu si vždy
 * prečíta z `models.owner_chat_id` tej modelky, presne ako to robí bot cez
 * `cfg.owner_chat_id`. Z prehliadača sa teda nedá poslať cudzie číslo a zmazať
 * niekomu skutočnú konverzáciu; jediné, čo sa dá vymazať, je chat, ktorý si sám
 * spároval. Vlastníctvo modelky overuje `ownedModel` user-scoped klientom (RLS),
 * až potom sa siahne po service kľúči — ten RLS obchádza, takže každý dotaz má
 * navyše `model_id` filter.
 *
 * ROZSAH. Presne tie tabuľky, ktoré maže worker, a v tom istom poradí: správy,
 * záznamy o odoslaných fotkách a hlasovkách, fakty, epizódy, otvorené sľuby a
 * tvrdenia o sebe. Nič mimo `(model_id, tg_id)` — ostatné konverzácie sa
 * nedotkne ani jeden príkaz.
 *
 * `last_msg_id` sa ZÁMERNE nenuluje (rovnako ako v `db.py`): Telegram si históriu
 * drží aj po vymazaní tej našej a Reconciler by pri nule stiahol posledných
 * tridsať správ a odpovedal na ne, akoby prišli teraz.
 */
export type WipeResult = { ok?: boolean; error?: string; deleted?: number };

/** Tabuľky, z ktorých sa maže — 1:1 s `db.wipe_conversation`. */
const WIPE_TABLES = [
  "dm_messages",
  "photo_sends",
  "voice_sends",
  "facts",
  "episodes",
  "open_loops",
  "self_claims",
] as const;

/** Reset riadku v `dm_users` — 1:1 s `db.wipe_conversation`. */
const WIPE_USER_RESET = {
  msg_count: 0,
  funnel_stage: "cold",
  summary: "",
  summary_at_msg: 0,
  style_note: "",
  partner_name: "",
  name_asked: false,
  asked_topics: {},
  used_gags: {},
  link_sent_at: null,
  link_push_count: 0,
  paid: false,
  human_takeover: false,
  pending_reply: false,
  reply_after: null,
  notified: false,
  last_incoming_at: null,
  last_reply_at: null,
  last_photo_at: null,
  last_voice_at: null,
  last_outreach_at: null,
  outreach_silent: 0,
  tidied_at: null,
} as const;

export async function wipeTestChatAction(modelId: string): Promise<WipeResult> {
  const model = await ownedModel(modelId);
  if (!model) return { error: "Model not found." };

  const tgId = model.owner_chat_id;
  if (!tgId) {
    return { error: "Nothing to wipe — no private Telegram is paired with this model." };
  }

  const admin = createServiceClient();

  // Počet správ pred mazaním — je to jediné číslo, ktoré vieme klientovi
  // úprimne povedať („koľko toho zmizlo"), a po delete už neexistuje.
  const { count } = await admin
    .from("dm_messages")
    .select("id", { count: "exact", head: true })
    .eq("model_id", model.id)
    .eq("tg_id", tgId);

  for (const table of WIPE_TABLES) {
    const { error } = await admin
      .from(table)
      .delete()
      .eq("model_id", model.id)
      .eq("tg_id", tgId);
    if (error) return { error: `Could not clear ${table}: ${error.message}` };
  }

  const { error: resetError } = await admin
    .from("dm_users")
    .update(WIPE_USER_RESET)
    .eq("model_id", model.id)
    .eq("tg_id", tgId);
  if (resetError) return { error: resetError.message };

  revalidatePath(`/app/m/${model.id}/telegram`, "layout");
  return { ok: true, deleted: count ?? 0 };
}

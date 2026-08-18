/**
 * Kontroly troch hodnôt, ktoré klient prepisuje ručne: `api_id`, `api_hash`
 * a token kontrolného bota.
 *
 * PREČO SAMOSTATNÝ SÚBOR. Prvý platiaci klient vlepil BotFatherov token bota do
 * políčka `api_id` a dozvedel sa to až o dva kroky ďalej — pri „Send code" mu
 * pod políčkom s TELEFÓNOM vyskočila veta o `api_id`. Chyba teda existovala len
 * na serveri a hlásila sa na úplne inom mieste, než vznikla. Tu sú preto
 * pravidlá raz, bez `"use server"` aj bez `"use client"`, takže tie isté funkcie
 * volá políčko pri opustení (okamžitá odozva) aj server action (autorita —
 * klientskej kontrole sa nikdy neverí).
 *
 * A druhá vec, dôležitejšia než samotná validácia: keď hodnota nesedí, nestačí
 * povedať „zlý formát". Ak sa dá rozpoznať, ČO tam klient vlepil, treba to
 * pomenovať a poslať ho na správne políčko.
 */

/** `api_hash` z my.telegram.org — presne 32 hex znakov. */
export const API_HASH_RE = /^[a-fA-F0-9]{32}$/;

/** Token od @BotFathera: `123456789:AAE…`. */
export const BOT_TOKEN_RE = /^\d{6,12}:[A-Za-z0-9_-]{30,}$/;

/** Telefón v medzinárodnom tvare. */
export const PHONE_RE = /^\+[1-9]\d{6,14}$/;

/** Postgres `integer` — nad to sa `models.tg_api_id` nezmestí. */
const API_ID_MAX = 2_147_483_647;

/**
 * Tvar tokenu bota, POZNANÝ VOĽNEJŠIE než `BOT_TOKEN_RE`.
 *
 * Na rozpoznanie omylu sa nesmie použiť prísna verzia: klient býva vlepí token
 * useknutý alebo s iným počtom znakov a práve vtedy potrebuje počuť „toto je
 * token bota", nie „api_id musí byť číslo".
 */
const BOT_TOKEN_SHAPE_RE = /^\d+:[\w-]{20,}$/;

export type FieldCheck = { ok: true } | { ok: false; message: string };

const OK: FieldCheck = { ok: true };

/**
 * Nesprávne políčko sa pomenúva slovami, ktoré klient vidí na obrazovke —
 * „Control bot step", nie `control_bot_token_enc`.
 */
const TOKEN_BELONGS =
  "That looks like a BotFather bot token. It belongs in the Control bot step, not here. " +
  "api_id is just a number from my.telegram.org.";

const API_ID_BELONGS =
  "That looks like your api_id, not the bot token. The bot token has a colon in it, " +
  "like 123456789:AAE… — BotFather sends it in the chat.";

export function looksLikeBotToken(value: string): boolean {
  return BOT_TOKEN_SHAPE_RE.test(value.trim());
}

/** Samé číslice a žiadna dvojbodka — teda `api_id`, nie token. */
export function looksLikeApiId(value: string): boolean {
  return /^\d{4,12}$/.test(value.trim());
}

/**
 * `api_id`. Prázdna hodnota je `ok` — či je políčko vyplnené, rieši ten, kto sa
 * pýta (pri opustení políčka sa na prázdne nenadáva, pri „Continue" áno).
 */
export function checkApiId(raw: string): FieldCheck {
  const value = raw.trim();
  if (!value) return OK;

  if (looksLikeBotToken(value)) return { ok: false, message: TOKEN_BELONGS };

  // 32 hex znakov je api_hash — druhá polovica tej istej dvojice, len prehodená.
  if (API_HASH_RE.test(value)) {
    return {
      ok: false,
      message: "That is the api_hash, not the api_id. The api_id is the short number above it.",
    };
  }

  const parsed = Number(value);
  if (!/^\d+$/.test(value) || !Number.isInteger(parsed) || parsed <= 0) {
    return {
      ok: false,
      message:
        "api_id is just digits — the number my.telegram.org shows as “App api_id”, " +
        "usually 7 or 8 digits.",
    };
  }
  if (parsed > API_ID_MAX) {
    return { ok: false, message: "That number is too long to be an api_id. Check it again." };
  }
  return OK;
}

/** `api_hash`. */
export function checkApiHash(raw: string): FieldCheck {
  const value = raw.trim();
  if (!value) return OK;

  if (looksLikeBotToken(value)) return { ok: false, message: TOKEN_BELONGS };

  if (/^\d+$/.test(value)) {
    return {
      ok: false,
      message: "That is the api_id. The api_hash is the long line under it, 32 characters.",
    };
  }
  if (!API_HASH_RE.test(value)) {
    return {
      ok: false,
      message: `api_hash is exactly 32 characters, digits and letters a–f (you pasted ${value.length}).`,
    };
  }
  return OK;
}

/** Token kontrolného bota. */
export function checkBotToken(raw: string): FieldCheck {
  const value = raw.trim();
  if (!value) return OK;

  if (looksLikeApiId(value)) return { ok: false, message: API_ID_BELONGS };
  if (API_HASH_RE.test(value)) {
    return { ok: false, message: "That looks like your api_hash, not the bot token." };
  }
  if (!BOT_TOKEN_RE.test(value)) {
    return {
      ok: false,
      message:
        "That is not a bot token. BotFather sends one long line with a colon in the middle, " +
        "like 123456789:AAE…",
    };
  }
  return OK;
}

export function checkPhone(raw: string): FieldCheck {
  const value = raw.replace(/[\s()-]/g, "");
  if (!value) return OK;
  if (!value.startsWith("+")) {
    return {
      ok: false,
      message: "Start with + and the country code, e.g. +421901234567.",
    };
  }
  if (!PHONE_RE.test(value)) {
    return { ok: false, message: "That is not a full phone number. Example: +421901234567." };
  }
  return OK;
}

/** Ručne prepísaný chat id (pokročilá záložná cesta k párovaniu). */
export function checkChatId(raw: string): FieldCheck {
  const value = raw.trim();
  if (!value) return OK;
  if (!/^-?\d{1,19}$/.test(value)) {
    return { ok: false, message: "A chat ID is only digits (a group ID starts with a minus)." };
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed === 0) {
    return { ok: false, message: "That is not a usable chat ID." };
  }
  return OK;
}

/** Normalizovaný telefón pre server (klient smie písať medzery a zátvorky). */
export function normalizePhone(raw: string): string {
  return raw.replace(/[\s()-]/g, "");
}

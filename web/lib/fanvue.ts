/**
 * Fanvue — OAuth 2.0 + PKCE, volania do ich API a overenie podpisu webhookov.
 *
 * Port `simona-dashboard/lib/fanvue.ts`. Protokolová časť (SCOPES, API_VERSION,
 * PKCE, výmena kódu, podpis) je prebraná doslova — je to kontrakt s cudzím
 * serverom, nie naše rozhodnutie. Zmenilo sa len okolie: v predlohe bola jedna
 * modelka = jedna DB schéma, tu je všetko v `public` a rozlišuje `model_id`.
 *
 * Fanvue nemá API kľúče, iba OAuth s POVINNÝM PKCE. Modelka teda musí raz
 * prekliknúť ich prihlasovaciu stránku a odvtedy držíme dvojicu tokenov:
 * prístupový žije hodinu, obnovovací ho vyrába ďalej. Obnovu robí worker
 * (`worker/src/fanvue_api.py`), web len pripája a odpája.
 */

import { createClient } from "@/lib/supabase/server";

const AUTH = "https://auth.fanvue.com/oauth2";
const API = "https://api.fanvue.com";

/** Fanvue vyžaduje túto hlavičku na každom volaní. Bez nej vracia 400. */
export const API_VERSION = "2025-06-26";

/**
 * Práva, ktoré si pýtame. Musia sedieť s tým, čo je zaškrtnuté v appke.
 *
 * Pýta sa len to, čo naozaj používame — každé právo navyše je riziko, že appka
 * ho nemá definované a celé prihlásenie spadne na `invalid_scope`.
 *
 * `read:creator` vyzerá zbytočne, kým sa nesiahne po vaulte: jeho endpointy
 * sedia pod `/creators/{uuid}/…` a bez neho vracajú 403 „Insufficient scopes“,
 * aj keď `read:media` povolené je.
 *
 * Pozor: token si nesie tie práva, s ktorými bol vydaný. Doplniť ich v appke
 * nestačí — účet sa musí pripojiť znova, inak beží ďalej so starou sadou.
 */
export const SCOPES = [
  "openid",
  "offline_access",
  "offline",
  "read:self",
  "read:chat",
  "write:chat",
  "read:fan",
  "read:creator",
  "read:media",
  "write:media",
  "read:post",
  "write:post",
  "read:insights",
  "read:tracking_links",
  "write:tracking_links",
].join(" ");

export type Tokens = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  scope: string;
};

export type Me = { uuid: string; handle?: string; displayName?: string };

function creds() {
  const id = process.env.FANVUE_CLIENT_ID;
  const secret = process.env.FANVUE_CLIENT_SECRET;
  if (!id || !secret) {
    throw new Error("Fanvue is not configured yet (FANVUE_CLIENT_ID / FANVUE_CLIENT_SECRET).");
  }
  return { id, secret };
}

/** Kam sa Fanvue vráti po prihlásení. Musí sedieť znak po znaku s appkou. */
export function redirectUri(origin: string): string {
  return process.env.FANVUE_REDIRECT_URI || `${origin}/api/fanvue/callback`;
}

function base64url(bytes: Uint8Array): string {
  let raw = "";
  for (const b of bytes) raw += String.fromCharCode(b);
  return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomToken(): string {
  return base64url(crypto.getRandomValues(new Uint8Array(32)));
}

/**
 * PKCE: z náhodného reťazca sa spraví odtlačok, ktorý ide na Fanvue. Samotný
 * reťazec ostáva u nás v cookie — keby niekto odchytil návratový kód, bez neho
 * ho na tokeny nevymení.
 */
export async function challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

export async function authorizeUrl(origin: string, state: string, verifier: string) {
  const url = new URL(`${AUTH}/auth`);
  url.searchParams.set("client_id", creds().id);
  url.searchParams.set("redirect_uri", redirectUri(origin));
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", SCOPES);
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", await challenge(verifier));
  url.searchParams.set("code_challenge_method", "S256");
  return url.toString();
}

/** Údaje appky idú v hlavičke, nie v tele — Fanvue iný spôsob neberie. */
async function token(body: URLSearchParams): Promise<Tokens> {
  const { id, secret } = creds();
  const basic = Buffer.from(`${id}:${secret}`).toString("base64");
  const r = await fetch(`${AUTH}/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${basic}`,
    },
    body,
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`Fanvue token ${r.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text) as Tokens;
}

export function exchangeCode(origin: string, code: string, verifier: string) {
  return token(
    new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(origin),
      code_verifier: verifier,
    }),
  );
}

export function refreshTokens(refresh: string) {
  return token(new URLSearchParams({ grant_type: "refresh_token", refresh_token: refresh }));
}

export async function apiGet<T>(accessToken: string, path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "X-Fanvue-API-Version": API_VERSION,
    },
    cache: "no-store",
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`Fanvue GET ${path} → ${r.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text) as T;
}

/** Kto je pripojený. Slúži aj ako overenie, že token naozaj funguje. */
export function whoami(accessToken: string) {
  return apiGet<Me>(accessToken, "/users/me");
}

/**
 * Overí podpis webhooku.
 *
 * Hlavička `x-fanvue-signature` vyzerá `t=1699…,v0=abc…` a podpisuje sa reťazec
 * `{timestamp}.{telo}` cez HMAC-SHA256 so signing secretom; výsledok je hex.
 * Telo musí byť presne to, čo prišlo po drôte — preparsovaním a späť by sa
 * podpis rozbil.
 *
 * Doručenia staršie ako 5 minút sa neprijímajú, inak by odchytený podpis
 * platil navždy. Porovnanie je v konštantnom čase.
 */
export async function validSignature(
  rawBody: string,
  header: string | null,
  secret: string,
): Promise<boolean> {
  if (!header || !secret) return false;
  let stamp = "";
  let sent = "";
  for (const part of header.split(",")) {
    const [k, v] = part.trim().split("=");
    if (k === "t") stamp = v ?? "";
    if (k === "v0") sent = v ?? "";
  }
  if (!stamp || !sent) return false;

  const age = Math.abs(Date.now() / 1000 - Number(stamp));
  if (!Number.isFinite(age) || age > 300) return false;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret) as BufferSource,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(`${stamp}.${rawBody}`) as BufferSource,
  );
  const expected = Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  if (expected.length !== sent.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ sent.charCodeAt(i);
  return diff === 0;
}

/* -------------------------------------------------------------------------- */
/*  Stav pripojenia pre UI                                                     */
/* -------------------------------------------------------------------------- */

/** Stĺpce, na ktoré má `authenticated` grant (migrácia 011). Tokeny medzi nimi
 *  zámerne nie sú — `select('*')` by skončil „permission denied for column…". */
export const FANVUE_COLUMNS =
  "model_id, connected, enabled, handle, display_name, creator_uuid, scope, " +
  "expires_at, last_error, updated_at";

export type FanvueConnection = {
  model_id: string;
  connected: boolean;
  enabled: boolean;
  handle: string;
  display_name: string;
  creator_uuid: string;
  scope: string;
  expires_at: string | null;
  last_error: string;
  updated_at: string | null;
};

const EMPTY: Omit<FanvueConnection, "model_id"> = {
  connected: false,
  enabled: false,
  handle: "",
  display_name: "",
  creator_uuid: "",
  scope: "",
  expires_at: null,
  last_error: "",
  updated_at: null,
};

/**
 * Stav pripojenia jednej modelky. Ide user-scoped klientom, takže cudzí riadok
 * RLS ani nevráti. Riadok zakladá trigger `provision_model_rows`, ale starším
 * modelkám (alebo po ručnom zásahu) chýbať môže — vtedy sa vráti prázdny stav.
 */
export async function getFanvueConnection(modelId: string): Promise<FanvueConnection> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("fanvue")
    .select(FANVUE_COLUMNS)
    .eq("model_id", modelId)
    .maybeSingle();

  return { model_id: modelId, ...EMPTY, ...((data as Partial<FanvueConnection>) ?? {}) };
}

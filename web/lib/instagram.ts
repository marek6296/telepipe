/**
 * Instagram — pripojenie cez oficiálne API.
 *
 * PREČO OFICIÁLNE. Telegram beží cez Telethon session, lebo inak sa to nedá.
 * Instagram oficiálne API má, takže sa použije: prihlásenie menom a heslom by
 * znamenalo ban účtu, o ktorý klientovi ide najviac.
 *
 * FACEBOOK STRÁNKA NETREBA. Overené v dokumentácii „Instagram API with
 * Instagram Login" (Meta, aktualizované 13. 3. 2026): „This API setup does not
 * require a Facebook Page to be linked to the Instagram professional account."
 * Stačí profesionálny účet — business alebo creator.
 *
 * ŽIVOTNOSŤ TOKENU
 * ----------------
 *   kód z presmerovania      platí 1 hodinu, na jedno použitie
 *   krátkodobý token         z kódu, cez api.instagram.com
 *   dlhodobý token           60 dní, cez graph.instagram.com/access_token
 *   obnovenie                ďalších 60 dní, ale LEN kým je platný
 *
 * Token, ktorý sa 60 dní neobnovil, je nenávratne mŕtvy a klient sa musí
 * pripojiť nanovo. Preto sa ukladá `token_expires_at` a preto existuje
 * `/api/instagram/refresh` — bez toho by modelka dva mesiace po pripojení
 * prestala odpisovať a nikto by nevedel prečo.
 *
 * PRÍSTUPOVÁ ÚROVEŇ. Meta rozlišuje Standard (účty, ktoré appka vlastní a má
 * pridané v App Dashboarde) a Advanced (cudzie účty, teda klienti). Kým appka
 * neprejde review na Advanced, funguje to len na účtoch pridaných ručne — čo
 * je presne to, čo teraz treba na testovanie.
 */

const AUTHORIZE = "https://www.instagram.com/oauth/authorize";
const TOKEN = "https://api.instagram.com/oauth/access_token";
const GRAPH = "https://graph.instagram.com";

/**
 * Oprávnenia, ktoré pýtame. `manage_messages` je jadro veci (DM), `basic` je
 * podmienka obnovovania tokenu, `manage_comments` je pre odpovede pod
 * príspevkami. Publikovanie obsahu NEPÝTAME — appka nič nepostuje a každé
 * oprávnenie navyše je ďalší dôvod, prečo by review neprešlo.
 */
export const SCOPES = [
  "instagram_business_basic",
  "instagram_business_manage_messages",
  "instagram_business_manage_comments",
] as const;

export type InstagramTokens = {
  accessToken: string;
  /** Sekundy do vypršania. Pri dlhodobom tokene ~60 dní. */
  expiresIn: number;
  userId: string;
  permissions: string;
};

export type InstagramProfile = {
  id: string;
  username: string;
  accountType: string;
};

function appId(): string {
  return process.env.INSTAGRAM_APP_ID?.trim() ?? "";
}

function appSecret(): string {
  return process.env.INSTAGRAM_APP_SECRET?.trim() ?? "";
}

/** Je pripojenie Instagramu vôbec nakonfigurované? UI podľa toho skryje tlačidlo. */
export function instagramConfigured(): boolean {
  return Boolean(appId() && appSecret());
}

/** Adresa, na ktorú sa Meta vracia. Musí PRESNE sedieť s App Dashboardom. */
export function redirectUri(origin: string): string {
  return `${origin.replace(/\/+$/, "")}/api/instagram/callback`;
}

/**
 * Kam poslať klienta, aby povolil prístup.
 *
 * `force_reauth` je zapnuté zámerne: majiteľ býva v prehliadači prihlásený pod
 * svojím súkromným Instagramom a bez toho by omylom pripojil ten.
 */
export function authorizeUrl(origin: string, state: string): string {
  if (!instagramConfigured()) {
    throw new Error("Instagram is not configured on this deployment.");
  }
  const params = new URLSearchParams({
    client_id: appId(),
    redirect_uri: redirectUri(origin),
    response_type: "code",
    scope: SCOPES.join(","),
    state,
    force_reauth: "true",
  });
  return `${AUTHORIZE}?${params.toString()}`;
}

/** Kód z presmerovania → krátkodobý token. Kód platí hodinu a len raz. */
export async function exchangeCode(
  origin: string,
  code: string,
): Promise<InstagramTokens> {
  const body = new FormData();
  body.set("client_id", appId());
  body.set("client_secret", appSecret());
  body.set("grant_type", "authorization_code");
  body.set("redirect_uri", redirectUri(origin));
  // Meta pripája k adrese „#_" a to nie je súčasť kódu.
  body.set("code", code.replace(/#_$/, ""));

  const response = await fetch(TOKEN, { method: "POST", body });
  const json = (await response.json()) as Record<string, unknown>;
  if (!response.ok) throw new Error(chyba(json, "Instagram rejected the code."));

  // Odpoveď chodí zabalená v poli `data`.
  const prvy = (Array.isArray(json.data) ? json.data[0] : json) as Record<string, unknown>;
  const accessToken = String(prvy.access_token ?? "");
  if (!accessToken) throw new Error("Instagram returned no access token.");

  return {
    accessToken,
    expiresIn: Number(prvy.expires_in ?? 3600),
    userId: String(prvy.user_id ?? ""),
    permissions: String(prvy.permissions ?? ""),
  };
}

/** Krátkodobý token → dlhodobý (60 dní). Ide výhradne zo servera — je v ňom secret. */
export async function longLivedToken(shortToken: string): Promise<InstagramTokens> {
  const params = new URLSearchParams({
    grant_type: "ig_exchange_token",
    client_secret: appSecret(),
    access_token: shortToken,
  });
  const response = await fetch(`${GRAPH}/access_token?${params}`);
  const json = (await response.json()) as Record<string, unknown>;
  if (!response.ok) throw new Error(chyba(json, "Instagram refused the long-lived token."));

  return {
    accessToken: String(json.access_token ?? ""),
    expiresIn: Number(json.expires_in ?? 0),
    userId: "",
    permissions: "",
  };
}

/**
 * Predĺženie o ďalších 60 dní.
 *
 * Podmienky podľa dokumentácie: token musí byť starší než 24 hodín, ešte
 * platný, a účet musí mať `instagram_business_basic`.
 */
export async function refreshToken(longToken: string): Promise<InstagramTokens> {
  const params = new URLSearchParams({
    grant_type: "ig_refresh_token",
    access_token: longToken,
  });
  const response = await fetch(`${GRAPH}/refresh_access_token?${params}`);
  const json = (await response.json()) as Record<string, unknown>;
  if (!response.ok) throw new Error(chyba(json, "Instagram refused to refresh the token."));

  return {
    accessToken: String(json.access_token ?? ""),
    expiresIn: Number(json.expires_in ?? 0),
    userId: "",
    permissions: "",
  };
}

/** Kto to vlastne pripojil. Bez toho by karta ukazovala „pripojené" bez mena. */
export async function profile(token: string): Promise<InstagramProfile> {
  const params = new URLSearchParams({
    fields: "id,username,account_type",
    access_token: token,
  });
  const response = await fetch(`${GRAPH}/me?${params}`);
  const json = (await response.json()) as Record<string, unknown>;
  if (!response.ok) throw new Error(chyba(json, "Instagram did not return the profile."));

  return {
    id: String(json.id ?? ""),
    username: String(json.username ?? ""),
    accountType: String(json.account_type ?? ""),
  };
}

/** Náhodný `state` proti CSRF. Rovnaký postup ako pri Fanvue. */
export function randomToken(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Chyba od Mety v čitateľnej podobe.
 *
 * Meta vracia raz `error_message`, raz `error.message` — a klient, ktorý sa
 * nepripojil, potrebuje vedieť prečo, nie „something went wrong".
 */
function chyba(json: Record<string, unknown>, fallback: string): string {
  const vnorena = json.error as Record<string, unknown> | undefined;
  const text =
    (json.error_message as string) ||
    (vnorena?.message as string) ||
    (json.error_description as string) ||
    "";
  return text ? `${fallback} ${text}` : fallback;
}

/* --------------------------------------------------------------------------
   Nastavenia agenta
-------------------------------------------------------------------------- */

export type InstagramFunnelTarget = "telegram" | "bio_link";

export type InstagramRow = {
  model_id: string;
  connected: boolean;
  enabled: boolean;
  ig_user_id: string;
  username: string;
  account_type: string;
  funnel_target: InstagramFunnelTarget;
  telegram_handle: string;
  bio_link: string;
  reply_mode: "off" | "auto" | "semi";
  heat: "mild" | "medium";
  reply_comments: boolean;
  token_expires_at: string | null;
  last_error: string;
  connected_at: string | null;
};

export const INSTAGRAM_COLUMNS =
  "model_id, connected, enabled, ig_user_id, username, account_type, " +
  "funnel_target, telegram_handle, bio_link, reply_mode, heat, reply_comments, " +
  "token_expires_at, last_error, connected_at";

export const INSTAGRAM_DEFAULTS: InstagramRow = {
  model_id: "",
  connected: false,
  enabled: false,
  ig_user_id: "",
  username: "",
  account_type: "",
  funnel_target: "telegram",
  telegram_handle: "",
  bio_link: "",
  reply_mode: "off",
  heat: "mild",
  reply_comments: false,
  token_expires_at: null,
  last_error: "",
  connected_at: null,
};

/** Koľko dní ešte token vydrží. `null` = nepripojené alebo neznáme. */
export function daysLeft(expiresAt: string | null): number | null {
  if (!expiresAt) return null;
  const koniec = new Date(expiresAt).getTime();
  if (Number.isNaN(koniec)) return null;
  return Math.max(0, Math.ceil((koniec - Date.now()) / 86_400_000));
}

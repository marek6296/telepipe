/** Instagram API with Unified Login. Tokens stay server-side. */
const AUTHORIZE = "https://www.facebook.com/dialog/oauth";
const GRAPH = "https://graph.facebook.com/v27.0";
export const SCOPES = ["instagram_basic", "instagram_manage_messages", "instagram_manage_comments", "instagram_content_publish", "instagram_manage_insights", "instagram_manage_events"] as const;
export type InstagramTokens = {accessToken: string; expiresIn: number; userId: string; permissions: string};
export type InstagramProfile = {id: string; username: string; accountType: string; businessId: string};
const appId = () => process.env.INSTAGRAM_APP_ID?.trim() ?? "";
const appSecret = () => process.env.INSTAGRAM_APP_SECRET?.trim() ?? "";
export const configId = () => process.env.INSTAGRAM_CONFIG_ID?.trim() ?? "";
export function instagramConfigured(): boolean { return Boolean(appId() && appSecret() && configId()); }
export function redirectUri(origin: string): string { return `${origin.replace(/\/+$/, "")}/api/instagram/callback`; }
export function authorizeUrl(origin: string, state: string): string {
  if (!instagramConfigured()) throw new Error("Instagram is not configured on this deployment.");
  return `${AUTHORIZE}?${new URLSearchParams({client_id:appId(),config_id:configId(),redirect_uri:redirectUri(origin),response_type:"code",override_default_response_type:"true",state,prompt:"login"})}`;
}
function message(json: Record<string, unknown>, fallback: string): string {
  const error = json.error as Record<string, unknown> | undefined;
  // Never reflect third-party payloads containing credentials into redirect URLs.
  return error?.code ? `${fallback} (Meta code ${String(error.code)})` : fallback;
}
async function graph(path: string, token: string, fields: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${GRAPH}/${path}?${new URLSearchParams({fields})}`, {headers:{Authorization:`Bearer ${token}`},cache:"no-store"});
  const json = await response.json() as Record<string, unknown>;
  if (!response.ok || json.error) throw new Error(message(json,"Instagram could not read this account. Please reconnect."));
  return json;
}
export async function exchangeCode(origin: string, code: string): Promise<InstagramTokens> {
  const params = new URLSearchParams({client_id:appId(),client_secret:appSecret(),code,redirect_uri:redirectUri(origin)});
  const response = await fetch(`${GRAPH}/oauth/access_token?${params}`,{cache:"no-store"});
  const json = await response.json() as Record<string, unknown>;
  if (!response.ok || !json.access_token) throw new Error(message(json,"Meta rejected the login. Please try connecting again."));
  return {accessToken:String(json.access_token),expiresIn:Number(json.expires_in ?? 0),userId:"",permissions:SCOPES.join(",")};
}
export async function profile(token: string): Promise<InstagramProfile> {
  const accounts = await graph("me/assigned_instagram_accounts",token,"id,username");
  const rows = Array.isArray(accounts.data) ? accounts.data as Record<string,unknown>[] : [];
  if (rows.length !== 1 || accounts.paging && (accounts.paging as Record<string,unknown>).next) throw new Error("Select exactly one Instagram account when connecting. Please try again.");
  const id = String(rows[0].id ?? "");
  if (!id) throw new Error("Meta returned no Instagram account. Share a professional Instagram account and try again.");
  const business = await graph("me",token,"client_business_id");
  if (!business.client_business_id) throw new Error("Meta returned no business portfolio. Please reconnect.");
  const account = await graph(id,token,"id,username");
  return {id,username:String(account.username ?? rows[0].username ?? ""),accountType:"PROFESSIONAL",businessId:String(business.client_business_id)};
}
/** Only legacy Instagram User tokens use this endpoint; SUATs must be excluded by callers. */
export async function refreshToken(token: string): Promise<InstagramTokens> {
  const response = await fetch(`https://graph.instagram.com/refresh_access_token?${new URLSearchParams({grant_type:"ig_refresh_token",access_token:token})}`,{cache:"no-store"});
  const json=await response.json() as Record<string,unknown>;
  if(!response.ok || !json.access_token) throw new Error("Instagram could not renew access. Please reconnect.");
  return {accessToken:String(json.access_token),expiresIn:Number(json.expires_in ?? 0),userId:"",permissions:""};
}
export function randomToken(): string {
 const bytes = new Uint8Array(24); crypto.getRandomValues(bytes);
 return Array.from(bytes,b=>b.toString(16).padStart(2,"0")).join("");
}

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

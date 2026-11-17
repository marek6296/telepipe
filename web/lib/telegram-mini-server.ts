import "server-only";
import { randomBytes } from "node:crypto";
import { cookies, headers } from "next/headers";
import { decrypt } from "@/lib/crypto";
import { encryptionKey } from "@/lib/env";
import { MODEL_COLUMNS, type ModelRow } from "@/lib/models";
import { modelTypeHasTab } from "@/lib/model-types";
import { authorizeSocialOwner, SocialError, UUID } from "@/lib/social-policy";
import { createServiceClient } from "@/lib/supabase/server";
import { MINI_COOKIE, MINI_IDLE_SECONDS, MINI_INIT_MAX_AGE_SECONDS, MiniAuthError, miniBotFingerprint, miniTokenHash, validMiniToken, verifyTelegramInitDataSignature } from "@/lib/telegram-mini-policy";

type MiniSession = {bot_model_id:string;account_id:string;telegram_owner_id:number;init_hash:string;created_at:string;expires_at:string};
export const miniCookieOptions = {httpOnly:true,secure:true,sameSite:"none" as const,path:"/api",maxAge:MINI_IDLE_SECONDS};

async function credential(): Promise<string|null> {
  const authorization = (await headers()).get("authorization");
  if (authorization !== null) {
    if (!authorization.startsWith("Bearer ") || !validMiniToken(authorization.slice(7))) throw new MiniAuthError();
    return authorization.slice(7);
  }
  const token = (await cookies()).get(MINI_COOKIE)?.value;
  if (token === undefined) return null;
  if (!validMiniToken(token)) throw new MiniAuthError();
  return token;
}
export async function miniSession(required = true) {
  const token = await credential();
  if (!token) { if (required) throw new MiniAuthError(); return null; }
  const db = createServiceClient();
  const {data,error} = await db.rpc("telegram_mini_session",{p_token:miniTokenHash(token)});
  if (error) throw new MiniAuthError("Could not verify Telegram access. Try again.",503);
  if (!data) throw new MiniAuthError();
  return {token,session:data as MiniSession,db};
}
type Auth = NonNullable<Awaited<ReturnType<typeof miniSession>>>;

async function modelList(auth: Auth) {
  const {data,error} = await auth.db.from("models").select("id,name,model_type").eq("account_id",auth.session.account_id).order("created_at",{ascending:true}).limit(1000);
  if (error) throw new MiniAuthError("Could not load your models. Try again.",503);
  return (data || []).filter(m=>modelTypeHasTab(m.model_type,"social")).map(m=>({id:m.id as string,name:m.name as string}));
}
export async function miniModels(bot: unknown) {
  const auth = (await miniSession())!;
  if (typeof bot!=="string" || !UUID.test(bot) || auth.session.bot_model_id!==bot) throw new MiniAuthError();
  return {models:await modelList(auth),selectedModelId:auth.session.bot_model_id,expiresAt:auth.session.expires_at};
}
export async function bootstrapMini(bot: unknown, initData: unknown) {
  if (typeof bot !== "string" || !UUID.test(bot)) throw new MiniAuthError();
  const db = createServiceClient();
  const {data:model,error} = await db.from("models").select("id,account_id,model_type,owner_chat_id,control_bot_token_enc").eq("id",bot).maybeSingle();
  if (error) throw new MiniAuthError("Could not verify Telegram access. Try again.",503);
  if (!model || !modelTypeHasTab(model.model_type,"social") || !model.owner_chat_id || !model.control_bot_token_enc) throw new MiniAuthError();
  let token: string;
  try { token = await decrypt(model.control_bot_token_enc,encryptionKey()); } catch { throw new MiniAuthError(); }
  const verified = verifyTelegramInitDataSignature(initData,token);
  if (String(model.owner_chat_id) !== String(verified.ownerId)) throw new MiniAuthError();
  // An HTTP retry can reuse only the existing, live session for this exact launch.
  const existing = await miniSession(false).catch(error => {
    if (error instanceof MiniAuthError && error.status === 401) return null;
    throw error;
  });
  if (existing && existing.session.bot_model_id === bot && existing.session.init_hash === verified.initHash) {
    return {token:existing.token,expiresAt:existing.session.expires_at,models:await modelList(existing),selectedModelId:bot};
  }
  if (Math.floor(Date.now()/1000)-verified.authDate>MINI_INIT_MAX_AGE_SECONDS) throw new MiniAuthError();
  const opaque = randomBytes(32).toString("base64url");
  const {data:session,error:issueError} = await db.rpc("telegram_mini_issue",{p_bot:bot,p_account:model.account_id,p_owner:verified.ownerId,
    p_fingerprint:miniBotFingerprint(model.control_bot_token_enc),p_init:verified.initHash,p_token:miniTokenHash(opaque),p_auth_date:new Date(verified.authDate*1000).toISOString()});
  if (issueError) throw new MiniAuthError("Could not open Telegram access. Try again.",503);
  if (!session) throw new MiniAuthError("This Telegram launch was already used or its pairing changed. Close this window and reopen it from your bot.",409);
  const auth={token:opaque,session:session as MiniSession,db};
  return {token:opaque,expiresAt:auth.session.expires_at,models:await modelList(auth),selectedModelId:bot};
}
export async function refreshMini() {
  const auth = (await miniSession())!;
  const {data,error} = await auth.db.rpc("telegram_mini_refresh",{p_token:miniTokenHash(auth.token)});
  if (error) throw new MiniAuthError("Could not refresh Telegram access. Try again.",503);
  if (!data?.expires_at) throw new MiniAuthError();
  return {token:auth.token,expiresAt:String(data.expires_at)};
}

/** Only Social imports this adapter; getUser, /app and Supabase auth stay unchanged. */
export async function miniSocialContext(modelId: string) {
  try {
    const requestHeaders=await headers();
    if (!requestHeaders.has("authorization") && requestHeaders.get("x-telepipe-mini")!=="1") return null;
    const auth=await miniSession(false);
    if (!auth) throw new MiniAuthError();
    const [modelResult,roleResult]=await Promise.all([
      auth.db.from("models").select(MODEL_COLUMNS).eq("id",modelId).eq("account_id",auth.session.account_id).maybeSingle(),
      auth.db.from("accounts").select("role").eq("id",auth.session.account_id).maybeSingle(),
    ]);
    if (modelResult.error || roleResult.error) throw new SocialError("Could not verify your access.",503);
    const model=modelResult.data as ModelRow|null;
    const channels=authorizeSocialOwner(model,auth.session.account_id,String(roleResult.data?.role || ""));
    if (!model || !modelTypeHasTab(model.model_type,"social")) throw new SocialError("This workspace is not available.",404);
    return {model,userId:auth.session.account_id,channels:channels.filter(c=>modelTypeHasTab(model.model_type,c)),db:auth.db};
  } catch (error) {
    if (error instanceof MiniAuthError) throw new SocialError(error.message,error.status);
    throw error;
  }
}

export function miniRequestGuard(request: Request) {
  if (request.headers.get("origin") !== new URL(request.url).origin) throw new MiniAuthError("This request must come from the Mini App.",403);
  if (request.headers.get("sec-fetch-site") === "cross-site") throw new MiniAuthError("This request must come from the Mini App.",403);
}
export async function miniJson(request: Request): Promise<Record<string,unknown>> {
  if (!request.headers.get("content-type")?.startsWith("application/json")) throw new MiniAuthError("Expected a JSON request.",400);
  if (Number(request.headers.get("content-length") || 0)>32768) throw new MiniAuthError("This request is too large.",413);
  const reader=request.body?.getReader();
  if (!reader) throw new MiniAuthError("Invalid request.",400);
  const decoder=new TextDecoder();let text="",bytes=0;
  while (true) {
    const chunk=await reader.read();if (chunk.done) break;
    bytes+=chunk.value.byteLength;
    if (bytes>32768) { await reader.cancel();throw new MiniAuthError("This request is too large.",413); }
    text+=decoder.decode(chunk.value,{stream:true});
  }
  text+=decoder.decode();
  try { const data=JSON.parse(text); if (!data || typeof data!=="object" || Array.isArray(data)) throw new Error(); return data; }
  catch { throw new MiniAuthError("Invalid request.",400); }
}
export function miniError(error:unknown) {
  return error instanceof MiniAuthError || error instanceof SocialError ? {message:error.message,status:error.status}
    : {message:"Could not complete this request. Try again.",status:503};
}

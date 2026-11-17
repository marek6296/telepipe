import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const MINI_IDLE_SECONDS = 30 * 60;
export const MINI_INIT_MAX_AGE_SECONDS = 5 * 60;
export const MINI_COOKIE = "__Secure-telepipe_mini";
export class MiniAuthError extends Error {
  status: number;
  constructor(message = "Open Social sites again from your paired Telegram bot.", status = 401) {
    super(message); this.name = "MiniAuthError"; this.status = status;
  }
}
export function validMiniToken(value: unknown): value is string {
  return typeof value === "string" && value.length === 43 && /^[A-Za-z0-9_-]+$/.test(value);
}
export const miniTokenHash = (token: string) => createHash("sha256").update(token).digest("hex");
export const miniBotFingerprint = (encryptedToken: string) => createHash("md5").update(encryptedToken).digest("hex");

/** Official Telegram HMAC: all decoded fields except hash, including signature. */
export function verifyTelegramInitDataSignature(initData: unknown, botToken: string, nowSeconds = Math.floor(Date.now()/1000)) {
  if (typeof initData !== "string" || !initData || initData.length > 8192 || /%(?![\da-f]{2})/i.test(initData) || !botToken) throw new MiniAuthError();
  const params = new URLSearchParams(initData);
  const fields = new Map<string,string>();
  for (const [key,value] of params) {
    if (!key || fields.has(key)) throw new MiniAuthError();
    fields.set(key,value);
  }
  const hash = fields.get("hash");
  if (!hash || !/^[\da-f]{64}$/.test(hash)) throw new MiniAuthError();
  fields.delete("hash");
  const check = [...fields].sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0).map(([key,value]) => `${key}=${value}`).join("\n");
  const secret = createHmac("sha256","WebAppData").update(botToken).digest();
  const expected = createHmac("sha256",secret).update(check).digest();
  if (!timingSafeEqual(expected,Buffer.from(hash,"hex"))) throw new MiniAuthError();
  const rawDate = fields.get("auth_date") || "";
  const authDate = Number(rawDate);
  if (!/^\d{1,12}$/.test(rawDate) || !Number.isSafeInteger(authDate) || authDate > nowSeconds+30) throw new MiniAuthError();
  let user: {id?:unknown;is_bot?:unknown};
  try { user = JSON.parse(fields.get("user") || "null"); } catch { throw new MiniAuthError(); }
  if (!user || typeof user !== "object" || typeof user.id !== "number" || !Number.isSafeInteger(user.id) || user.id <= 0 || user.is_bot === true) throw new MiniAuthError();
  // Use the authenticated HMAC, not raw query ordering, for durable replay keys.
  return {ownerId:user.id,authDate,initHash:miniTokenHash(hash)};
}
export function validateTelegramInitData(initData: unknown, botToken: string, nowSeconds = Math.floor(Date.now()/1000)) {
  const verified=verifyTelegramInitDataSignature(initData,botToken,nowSeconds);
  if (nowSeconds-verified.authDate>MINI_INIT_MAX_AGE_SECONDS) throw new MiniAuthError();
  return verified;
}

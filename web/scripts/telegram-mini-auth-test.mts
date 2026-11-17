import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { validateTelegramInitData, miniTokenHash, validMiniToken, MiniAuthError } from "../lib/telegram-mini-policy.ts";

const now = 1_800_000_000;
const token = "123456:private-test-token";
function signed(fields: Record<string,string>, key = token) {
  const data = Object.entries(fields).sort(([a],[b]) => a.localeCompare(b)).map(([k,v]) => `${k}=${v}`).join("\n");
  const secret = createHmac("sha256", "WebAppData").update(key).digest();
  const hash = createHmac("sha256", secret).update(data).digest("hex");
  return new URLSearchParams({...fields,hash}).toString();
}
const fields = {auth_date:String(now),query_id:"launch-A",user:JSON.stringify({id:12345,first_name:"Owner & + name"}),signature:"signed-extra-field"};
const good = signed(fields);
assert.equal(validateTelegramInitData(good,token,now).ownerId,12345);
assert.equal(validateTelegramInitData(good,token,now+300).authDate,now);
for (const [name,value,key,time] of [
  ["wrong bot",good,"654321:other-token",now],
  ["forged owner",good.replace("12345","54321"),token,now],
  ["stale",good,token,now+301],
  ["future",signed({...fields,auth_date:String(now+31)}),token,now],
  ["duplicate user",good+"&user=%7B%7D",token,now],
  ["duplicate hash",good+"&hash="+"a".repeat(64),token,now],
  ["invalid date",signed({...fields,auth_date:"Infinity"}),token,now],
  ["string id",signed({...fields,user:JSON.stringify({id:"12345"})}),token,now],
  ["unsafe id",signed({...fields,user:JSON.stringify({id:2**54})}),token,now],
  ["bot user",signed({...fields,user:JSON.stringify({id:12345,is_bot:true})}),token,now],
  ["unsigned signature",good.replace("signed-extra-field","changed"),token,now],
  ["malformed escaping",good+"&x=%XX",token,now],
  ["oversize","x".repeat(8193),token,now],
] as const) assert.throws(()=>validateTelegramInitData(value,key,time),MiniAuthError,name);
assert.equal(validMiniToken("a".repeat(43)),true);
assert.equal(validMiniToken("a".repeat(42)),false);
assert.equal(validMiniToken("a".repeat(43)+"\n"),false);
assert.equal(miniTokenHash("a".repeat(43)).length,64);
assert.notEqual(miniTokenHash("a".repeat(43)),miniTokenHash("b".repeat(43)));
const config=readFileSync(new URL("../next.config.ts",import.meta.url),"utf8");
assert.match(config,/source:\s*"\/mini\/:path\*"/);
assert.ok(config.includes("frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"),"SameSite=None Mini cookies require Telegram-only frame ancestors");
console.log("Telegram Mini auth: HMAC, freshness, duplicates, bot/owner forgery and opaque token validation passed.");

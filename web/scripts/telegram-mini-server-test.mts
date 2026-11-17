import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import * as policy from "../lib/telegram-mini-policy.ts";
import * as social from "../lib/social-policy.ts";
const require=createRequire(import.meta.url);
const root=resolve(import.meta.dirname,"..");
const modelId="10000000-0000-0000-0000-000000000001",secondId="10000000-0000-0000-0000-000000000002";
const token="a".repeat(43),botToken="12345:secret-test-token";
const signed=(owner=12345,age=0)=>{
  const fields={auth_date:String(Math.floor(Date.now()/1000)-age),query_id:"launch",user:JSON.stringify({id:owner})};
  const secret=createHmac("sha256","WebAppData").update(botToken).digest();
  const hash=createHmac("sha256",secret).update(Object.entries(fields).map(([k,v])=>`${k}=${v}`).join("\n")).digest("hex");
  return new URLSearchParams({...fields,hash}).toString();
};
type Row=Record<string,unknown>;
let requestHeaders=new Headers(),cookie:string|undefined,serviceCalls=0,issueCalls=0;
let models:Row[]=[],session:Row|null=null,issueResult:Row|null=null;
function reset() {
 requestHeaders=new Headers();cookie=undefined;serviceCalls=0;issueCalls=0;
 models=[{id:modelId,account_id:"owner",name:"Own",model_type:"persona",owner_chat_id:12345,control_bot_token_enc:"ciphertext"},
 {id:secondId,account_id:"foreign",name:"Foreign",model_type:"persona",owner_chat_id:54321,control_bot_token_enc:"foreign-cipher"}];
 session={bot_model_id:modelId,account_id:"owner",telegram_owner_id:12345,init_hash:policy.validateTelegramInitData(signed(),botToken).initHash,expires_at:new Date(Date.now()+1800000).toISOString(),created_at:new Date().toISOString()};
 issueResult=session;
}
const client={
 from(table:string) {
  let single=false;const filters:[string,unknown][]=[];
  const builder=new Proxy({}, {get(_target,key:string) {
   if(key==="then") return (done:(x:unknown)=>unknown)=>{
    const rows=(table==="models"?models:[{id:"owner",role:"superadmin"}]).filter(r=>filters.every(([k,v])=>r[k]===v));
    return done({data:single?(rows[0] || null):rows,error:null});
   };
   return (...args:unknown[])=>{if(key==="eq")filters.push([String(args[0]),args[1]]);if(key==="maybeSingle")single=true;return builder;};
  }});return builder;
 },
 async rpc(name:string,args:Row) {
  if(name==="telegram_mini_session") { assert.equal(args.p_token,policy.miniTokenHash(token));return {data:session,error:null}; }
  if(name==="telegram_mini_issue") {issueCalls++;assert.equal(args.p_bot,modelId);assert.equal(args.p_owner,12345);assert.equal(args.p_account,"owner");assert.equal(String(args.p_token).length,64);assert.notEqual(args.p_token,token);return {data:issueResult,error:null};}
  if(name==="telegram_mini_refresh")return {data:session?{expires_at:session.expires_at}:null,error:null};
  throw Error(name);
 }
};
const mocks:Record<string,unknown>={
 "server-only":{},"next/headers":{headers:async()=>requestHeaders,cookies:async()=>({get:()=>cookie?{value:cookie}:undefined})},
 "@/lib/crypto":{decrypt:async()=>botToken},"@/lib/env":{encryptionKey:()=>"not-real"},
 "@/lib/models":{MODEL_COLUMNS:"id,account_id,name,model_type"},"@/lib/model-types":{modelTypeHasTab:(type:string)=>type==="persona"},
 "@/lib/social-policy":social,"@/lib/telegram-mini-policy":policy,
 "@/lib/supabase/server":{createServiceClient:()=>{serviceCalls++;return client;}},
};
const source=ts.transpileModule(readFileSync(resolve(root,"lib/telegram-mini-server.ts"),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const loaded={exports:{}};
vm.runInThisContext(`(function(require,module,exports){${source}\n})`,{filename:"telegram-mini-server.ts"})((name:string)=>mocks[name]??require(name),loaded,loaded.exports);
const api=loaded.exports as typeof import("../lib/telegram-mini-server");

reset();cookie=token;
assert.equal(await api.miniSocialContext(modelId),null,"A Mini cookie must not hijack ordinary web authentication");assert.equal(serviceCalls,0);
reset();requestHeaders.set("x-telepipe-mini","1");
await assert.rejects(api.miniSocialContext(modelId),e=>e instanceof social.SocialError&&e.status===401);
reset();requestHeaders.set("authorization","Bearer "+token);
assert.equal((await api.miniSocialContext(modelId))?.userId,"owner");
await assert.rejects(api.miniSocialContext(secondId),/not available/);
assert.deepEqual(await api.miniModels(modelId),{models:[{id:modelId,name:"Own"}],selectedModelId:modelId,expiresAt:(session as Row|null)?.expires_at});
await assert.rejects(api.miniModels(secondId),policy.MiniAuthError,"Another bot cannot restore this cookie session");
reset();cookie=token;requestHeaders.set("authorization","Bearer malformed");
await assert.rejects(api.miniSession(),policy.MiniAuthError,"Bad bearer never falls back to valid cookie");assert.equal(serviceCalls,0);
reset();cookie=token;requestHeaders.set("x-telepipe-mini","1");session=null;
await assert.rejects(api.miniSocialContext(modelId),e=>e instanceof social.SocialError&&e.status===401,"Revoked live pairing rejects shared Social access");
await assert.rejects(api.refreshMini(),policy.MiniAuthError);
reset();
for(const init of [signed(54321),signed().replace("12345","54321")])await assert.rejects(api.bootstrapMini(modelId,init),policy.MiniAuthError);
assert.equal(issueCalls,0);
models[0].owner_chat_id=null;await assert.rejects(api.bootstrapMini(modelId,signed()),policy.MiniAuthError);assert.equal(issueCalls,0);
reset();const opened=await api.bootstrapMini(modelId,signed());
assert.equal(opened.token.length,43);assert.equal(issueCalls,1);assert.deepEqual(opened.models,[{id:modelId,name:"Own"}]);
reset();cookie=token;
assert.equal((await api.bootstrapMini(modelId,signed())).token,token);assert.equal(issueCalls,0,"A retry with original live credential is idempotent");
reset();cookie=token;
const oldLaunch=signed(12345,600);session!.init_hash=policy.verifyTelegramInitDataSignature(oldLaunch,botToken).initHash;
assert.equal((await api.bootstrapMini(modelId,oldLaunch)).token,token,"An authenticated same-launch reload resumes without minting a session");assert.equal(issueCalls,0);
cookie=undefined;
await assert.rejects(api.bootstrapMini(modelId,oldLaunch),policy.MiniAuthError,"Old launch alone cannot create a session");assert.equal(issueCalls,0);
reset();cookie=token;models[0].owner_chat_id=54321;
await assert.rejects(api.bootstrapMini(modelId,signed()),policy.MiniAuthError,"Old cookie never bypasses signed owner validation");
reset();issueResult=null;
await assert.rejects(api.bootstrapMini(modelId,signed()),e=>e instanceof policy.MiniAuthError&&e.status===409,"Uncredentialled replay asks to reopen");
for(const origin of [null,"https://attacker.test"]){const req=new Request("https://telepipe.me/api/mini/actions",{method:"POST",headers:origin?{origin}:{}});assert.throws(()=>api.miniRequestGuard(req),policy.MiniAuthError);}
api.miniRequestGuard(new Request("https://telepipe.me/api/mini/actions",{method:"POST",headers:{origin:"https://telepipe.me"}}));
await assert.rejects(api.miniJson(new Request("https://telepipe.me/api/mini/actions",{method:"POST",headers:{"content-type":"application/json"},body:"[]"})),policy.MiniAuthError);
await assert.rejects(api.miniJson(new Request("https://telepipe.me/api/mini/actions",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({text:"x".repeat(32768)})})),e=>e instanceof policy.MiniAuthError&&e.status===413,"Unknown Content-Length is still bounded while streaming");
assert.equal(api.miniCookieOptions.httpOnly,true);assert.equal(api.miniCookieOptions.secure,true);assert.equal(api.miniCookieOptions.path,"/api");
console.log("Telegram Mini server: bootstrap, replay retry, live pairing, foreign tenant, mixed browser auth, scoped DTO, CSRF and cookie contracts passed.");

let dispatched:unknown[][]=[];
let authenticated=true;
mocks["@/lib/telegram-mini-server"]={...api,miniSession:async()=>{if(!authenticated)throw new policy.MiniAuthError();return {};}};
mocks["next/server"]={NextResponse:{json:(data:unknown,options:{status?:number})=>({data,status:options.status||200})}};
mocks["@/app/app/m/[id]/social/actions"]=Object.fromEntries(["submitSocialCommand","setSocialMode","setSocialTakeover","linkSocialContacts","unlinkSocialContact","skipSocialPending"].map(name=>[name,async(...args:unknown[])=>{dispatched.push([name,...args]);return {message:"ok"};}]));
const routeSource=ts.transpileModule(readFileSync(resolve(root,"app/api/mini/actions/route.ts"),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const routeLoaded={exports:{}};
vm.runInThisContext(`(function(require,module,exports){${routeSource}\n})`)((name:string)=>mocks[name]??require(name),routeLoaded,routeLoaded.exports);
const route=routeLoaded.exports as {POST:(request:Request)=>Promise<{status:number;data:unknown}>};
function actionRequest(body:unknown,extra:Record<string,string>={}) {return new Request("https://telepipe.me/api/mini/actions",{method:"POST",headers:{origin:"https://telepipe.me","content-type":"application/json","x-telepipe-mini":"1",...extra},body:JSON.stringify(body)});}
const input={requestId:secondId,operation:"regenerate",brief:"meaning in her voice"};
assert.equal((await route.POST(actionRequest({modelId,action:"command",input}))).status,200);
assert.deepEqual(dispatched,[["submitSocialCommand",modelId,input]],"Mini command uses the same durable server action without modifying the intent");
dispatched=[];
assert.equal((await route.POST(actionRequest({modelId,action:"takeover",contactKey:"telegram:123",takeover:false}))).status,200);
assert.deepEqual(dispatched,[["setSocialTakeover",modelId,"telegram:123",false]]);
dispatched=[];authenticated=false;
assert.equal((await route.POST(actionRequest({modelId,action:"mode",channel:"telegram",mode:"auto"}))).status,401);
assert.equal(dispatched.length,0,"A web login cannot replace a revoked Mini session");
authenticated=true;
assert.equal((await route.POST(actionRequest({modelId,action:"mode"},{origin:"https://attacker.test"}))).status,403);
assert.equal((await route.POST(actionRequest({modelId,action:"unknown"}))).status,400);
assert.equal((await route.POST(actionRequest({modelId,action:"mode"},{"x-telepipe-mini":""}))).status,401);
assert.equal(dispatched.length,0);
console.log("Telegram Mini actions: shared durable dispatch, explicit Mini realm, auth-before-mutation and CSRF passed.");

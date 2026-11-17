import assert from "node:assert/strict";
import { connectMiniSession, notificationTarget } from "../components/app/social/mini-session.ts";
import { createMiniTransport } from "../components/app/social/transport-core.ts";
const calls: {url:string; options:RequestInit}[] = [];
let status = 200;
let expired = 0;
const transport = createMiniTransport({token:"memory-only", onExpired:() => expired++, fetcher:async (url, options) => {
  calls.push({url:String(url),options:options!});
  return new Response(JSON.stringify(status === 200 ? {message:"Queued"} : {error:"Expired"}), {status});
}});
await transport.read("/api/models/model/social?search=hello");
assert.equal(calls[0].options.credentials,"include");
assert.equal(new Headers(calls[0].options.headers).get("Authorization"),"Bearer memory-only");
assert.equal(calls[0].options.redirect,"error");
assert.equal(new Headers(calls[0].options.headers).get("X-Telepipe-Mini"),"1");
await assert.rejects(() => transport.read("https://foreign.invalid/api/models/a/social"));
await assert.rejects(() => transport.read("//foreign.invalid/api/models/a/social"));
await assert.rejects(() => transport.read("/api/models/a/../../other"));
assert.equal(calls.length,1,"Bearer never leaves the allowed API paths");
await transport.setSocialMode("model","telegram","semi");
assert.deepEqual(JSON.parse(calls[1].options.body as string),{modelId:"model",action:"mode",channel:"telegram",mode:"semi"});
status = 503;
const input = {requestId:"same-intent",operation:"send_text"} as never;
assert.equal((await transport.submitSocialCommand("model",input)).retryable,true);
assert.equal(calls.length,3,"No automatic mutation retry");
status = 401;
await assert.rejects(() => transport.read("/api/models/model/social"));
assert.equal(expired,1);
await assert.rejects(() => transport.read("/api/models/model/social"));
assert.equal(calls.length,4,"An expired session cannot continue background polling");
console.log("PASS: Mini transport confines bearer, maps actions, preserves retries and expires closed");

const launches: {url:string;options:RequestInit}[] = [];
const fetchLaunch:typeof fetch = async (url, options) => { launches.push({url:String(url),options:options!}); return Response.json({models:[],selectedModelId:"bot-b"}); };
await connectMiniSession({bot:"bot-b",initData:"signed-launch-b",fetcher:fetchLaunch});
assert.equal(launches[0].url,"/api/mini/bootstrap","A signed launch cannot reuse another bot's cookie via models first");
assert.deepEqual(JSON.parse(launches[0].options.body as string),{bot:"bot-b",initData:"signed-launch-b"});
await connectMiniSession({bot:"bot-b",fetcher:fetchLaunch});
assert.equal(launches[1].url,"/api/mini/models?bot=bot-b","Cookie-only reload remains bound to launch bot");
await assert.rejects(() => connectMiniSession({bot:null,initData:"signed",fetcher:fetchLaunch}));
console.log("PASS: Mini launch always verifies current initData and binds cookie fallback to bot");

const ownerSession={models:[{id:"bot-a",name:"Simona"}],selectedModelId:"bot-a"};
for(const contact of ["instagram:123", "telegram:456", "fanvue:fan-uuid"])
  assert.deepEqual(notificationTarget(ownerSession,"bot-a",contact),{id:"bot-a",contact});
assert.equal(notificationTarget(ownerSession,"bot-a",null),null,"Normal menu launch keeps the model picker");
assert.equal(notificationTarget(ownerSession,"foreign","instagram:123"),null);
assert.equal(notificationTarget({...ownerSession,models:[]},"bot-a","instagram:123"),null);
for(const invalid of ["instagram:","other:123","instagram:bad id","https://evil.invalid","x".repeat(600)])
  assert.equal(notificationTarget(ownerSession,"bot-a",invalid),null);
console.log("PASS: notification launch selects only its verified model and valid channel/contact");

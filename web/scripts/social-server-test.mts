import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import vm from "node:vm";
import ts from "typescript";
import * as policy from "../lib/social-policy.ts";

const require = createRequire(import.meta.url);
const root = resolve(import.meta.dirname,"..");
const modelId = "10000000-0000-0000-0000-000000000001";
const actionId = "20000000-0000-0000-0000-000000000001";
let user: {id:string} | null = {id:"owner"};
let role = "superadmin", owner = "owner", serviceCalls = 0;
const calls: {table:string;method:string;args:unknown[]}[] = [];
let fixtures: Record<string,unknown> = {};
let rpcError: {code:string;message:string} | null = null;
function db() {
  return {from(table:string) {
    let single = false;
    const builder = new Proxy({}, {get(_target,method:string) {
      if (method === "then") return (done:(result:unknown)=>void) => done({data:fixtures[table] ?? (single ? null : []),error:null});
      return (...args:unknown[]) => { calls.push({table,method,args}); if (method === "maybeSingle") single=true; return builder; };
    }});
    return builder;
  },rpc(name:string,args:unknown) { calls.push({table:name,method:"rpc",args:[args]}); return Promise.resolve({data:fixtures[name] ?? true,error:rpcError}); }};
}
const mocks: Record<string,unknown> = {
  "server-only":{}, "next/cache":{revalidatePath() {}},
  "@/lib/telegram-mini-server":{miniSocialContext:async()=>null},
  "@/lib/social-media-server":{loadSocialMedia:async()=>fixtures.media || {}},
  "@/lib/models":{getModel:async () => ({id:modelId,account_id:owner,name:"Example",model_type:"persona",status:"active",claimed_by:"worker",heartbeat_at:new Date().toISOString()})},
  "@/lib/model-types":{modelTypeHasTab:() => true},
  "@/lib/supabase/server":{getUser:async () => user,createClient:async () => db(),createServiceClient:() => {serviceCalls++;return db();}},
  "@/lib/telegram":{getTelegramConnection:async () => ({connected:true,phone:null})},
  "@/lib/social-policy":policy,
  "@/lib/social-links":await import("../lib/social-links.ts"),
};
function moduleAt(path:string) {
  const source = ts.transpileModule(readFileSync(resolve(root,path),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const loaded = {exports:{}};
  vm.runInThisContext(`(function(require,module,exports){${source}\n})`,{filename:path})((name:string) => mocks[name] ?? require(name),loaded,loaded.exports);
  return loaded.exports as Record<string, (...args: unknown[]) => Promise<unknown>>;
}
const server = moduleAt("lib/social-server.ts"); mocks["@/lib/social-server"] = server;
const actions = moduleAt("app/app/m/[id]/social/actions.ts");
function reset() { calls.length=0; serviceCalls=0; user={id:"owner"};role="superadmin";owner="owner";rpcError=null;fixtures={accounts:{role}}; }

reset(); user=null;
await assert.rejects(server.socialContext(modelId),/Sign in/); assert.equal(serviceCalls,0);
reset(); owner="someone-else";
await assert.rejects(server.socialContext(modelId),/not available/); assert.equal(serviceCalls,0);
reset(); fixtures.accounts={role:"client"};
assert.match((await actions.setSocialMode(modelId,"instagram","auto") as {error:string}).error,/not available/);
assert.ok(!calls.some(c => c.method === "update" || c.method === "rpc"));

reset();
fixtures.social_contact_summaries={model_id:modelId,channel:"instagram",external_id:"123",account_scope:"account",identity_id:null,identity_updated_at:null,last_message_id:"42",last_message_role:"user",pending_id:null};
fixtures.ig_messages=[{id:42,role:"user",content:"Hello",occurred_at:null,created_at:"2026-11-16T20:00:00Z"}];
fixtures.social_commands=[{id:actionId,channel:"instagram",operation:"send_text",external_id:"123",status:"done",result:{action_id:actionId},text:"Hello"}];
fixtures.instagram_actions=[{id:actionId,state:"sent"}];
const thread = await server.loadSocialThread(modelId,"instagram:123") as {messages:{occurredAt:null}[];commands:{deliveryState:string}[]};
assert.equal(thread.messages[0].occurredAt,null);
assert.equal(thread.commands[0].deliveryState,"sent");
assert.ok(calls.some(c => c.table === "instagram_actions" && c.method === "select" && c.args[0] === "id,state"));
assert.ok(!calls.some(c => ["update","insert","rpc"].includes(c.method)),"Opening history must never mark seen or mutate state");
for (const table of ["social_contact_summaries","ig_messages","social_commands","instagram_actions"])
  assert.ok(calls.some(c => c.table === table && c.method === "eq" && c.args[0] === "model_id" && c.args[1] === modelId),`${table} must be tenant-scoped`);

reset();
const input={requestId:actionId,operation:"send_text",contactKey:"telegram:123",expectedSourceId:"42",expectedAccountScope:"primary",identityId:null,identityUpdatedAt:null,text:"Exact reply"};
fixtures.social_commands={id:actionId,idempotency_key:actionId,operation:"send_text",channel:"telegram",external_id:"123",account_scope:"primary",pending_id:null,expected_suggestions:null,expected_source_id:"42",identity_id:null,identity_updated_at:null,text:"Exact reply",brief:"",status:"done",result:{delivery_state:"sent"}};
const retry = await actions.submitSocialCommand(modelId,input) as {command:{deliveryState:string}};
assert.equal(retry.command.deliveryState,"sent");
assert.ok(!calls.some(c => c.method === "rpc" || c.table === "social_contact_summaries"),"Lost response retry must not enqueue or validate against newer history");
const tampered = await actions.submitSocialCommand(modelId,{...input,text:"Different"}) as {error:string};
assert.match(tampered.error,/different action/);

reset();
fixtures.social_contact_summaries={channel:"telegram",external_id:"123",account_scope:"primary",last_message_id:"42",identity_id:null,identity_updated_at:null,pending_id:null};
rpcError={code:"",message:"fetch failed after submission"};
assert.equal((await actions.submitSocialCommand(modelId,input) as {retryable:boolean}).retryable,true,"Unknown enqueue outcome must retain the same request ID");
rpcError={code:"P0001",message:"source_changed"};
assert.equal((await actions.submitSocialCommand(modelId,input) as {retryable:boolean}).retryable,false,"Confirmed SQL rejection permits review and a new intent");

reset();
fixtures.settings={model_id:modelId};
await actions.setSocialMode(modelId,"telegram","semi");
assert.ok(calls.some(c => c.table === "settings" && c.method === "update" && JSON.stringify(c.args[0]) === JSON.stringify({tg_reply_mode:"semi",tg_fallback_minutes:null})));
assert.ok(calls.some(c => c.table === "settings" && c.method === "eq" && c.args[1] === modelId));
console.log("Social server: auth, rollout, DTO, read-only history, source times, delivery state and retry checks passed.");

reset();
fixtures.social_contact_summaries={model_id:modelId,channel:"telegram",external_id:"987654",account_scope:"primary",identity_id:null,identity_updated_at:null,last_message_id:"42",pending_id:null};
fixtures.dm_messages=[{id:42,role:"user",content:"A contact outside the first inbox page",created_at:"2026-11-16T20:00:00Z"}];
const selected = await server.loadSocialSelection(modelId,"telegram:987654") as {thread:{contact:{key:string}};error:string|null};
assert.equal(selected.thread?.contact.key,"telegram:987654","A notification link opens its contact without relying on the inbox page");
assert.equal(selected.error,null);
assert.ok(!calls.some(c => c.table === "social_inbox"),"Selecting a contact is independent of inbox filtering and pagination");
assert.ok(!calls.some(c => ["update","insert","rpc"].includes(c.method)),"Opening a notification must never send, generate or mark seen");
reset();
for (const value of [["telegram:1","telegram:2"],"https://example.com","instagram:1:action-id",""]) {
  const invalid = await server.loadSocialSelection(modelId,value) as {thread:null;error:string|null};
  assert.equal(invalid.thread,null);
  assert.ok(invalid.error,"Malformed notification targets must show a selection error");
}
assert.equal(serviceCalls,0,"Invalid targets must be rejected before service reads");
assert.deepEqual(await server.loadSocialSelection(modelId,undefined),{thread:null,error:null});
reset();fixtures.accounts={role:"client"};
const unavailable = await server.loadSocialSelection(modelId,"instagram:123") as {thread:null;error:string};
assert.equal(unavailable.thread,null);
assert.match(unavailable.error,/not available/);
assert.ok(!calls.some(c => c.table === "social_contact_summaries"),"Deep links cannot bypass Instagram rollout gating");
console.log("Social notification links: independent contact loading, invalid inputs and rollout boundaries passed.");

reset();
fixtures.social_contact_summaries={channel:"telegram",external_id:"123",account_scope:"primary",last_message_id:"42",pending_id:null};
fixtures.dm_messages=[{id:42,role:"user",content:"Caption\n[Attachment audio: ready]\nTranscript: hello",created_at:"2026-11-16T20:00:00Z"}];
fixtures.media={"42":{originalContent:"Caption",media:[{id:actionId,kind:"audio",transcript:"hello"}]}};
const withMedia=await server.loadSocialThread(modelId,"telegram:123") as {messages:{content:string;media:{transcript:string}[]}[]};
assert.equal(withMedia.messages[0].content,"Caption","Human UI retains the original caption without duplicating analysis text");
assert.equal(withMedia.messages[0].media[0].transcript,"hello");

reset();owner='someone-else';
assert.match((await actions.dismissSocialCommand(modelId,'instagram:123',actionId) as {error:string}).error,/not available/);
assert.ok(!calls.some(c=>c.table==='social_dismiss_command'));
reset();
fixtures.social_contact_summaries={channel:'instagram',external_id:'123',account_scope:'account',last_message_id:'42',identity_id:null,identity_updated_at:null};
await actions.dismissSocialCommand(modelId,'instagram:123',actionId);
assert.ok(calls.some(c=>c.table==='social_dismiss_command' && (c.args[0] as {p_external:string}).p_external==='123'));
const draftContact={channel:'instagram',externalId:'123',accountScope:'account',lastMessageId:'42',identityId:null,identityUpdatedAt:null};
const ownerRow={id:actionId,operation:'regenerate',status:'done',pending_id:null,channel:'instagram',external_id:'123',expected_source_id:'42',account_scope:'account',identity_id:null,identity_updated_at:null,created_at:new Date().toISOString(),result:{owner_suggestions:['hey you']}};
assert.ok(await server.ownerDraftForContact([ownerRow],draftContact));
assert.equal(await server.ownerDraftForContact([ownerRow],{...draftContact,lastMessageId:'43'}),null);
assert.equal(await server.ownerDraftForContact([{...ownerRow,ui_dismissed_at:new Date().toISOString()}],draftContact),null);
console.log('PASS: owner-scoped presentation dismissal and source-bound independent suggestions');
assert.equal(await server.ownerDraftForContact([{...ownerRow,id:'latest',ui_dismissed_at:new Date().toISOString()},ownerRow],draftContact),null,'Skipping the latest owner draft must not resurface an older one');

reset();
fixtures.social_inbox={contacts:[{channel:'instagram',external_id:'123',account_scope:'current',last_message_role:'user'}],total:1};
fixtures.social_waiting_message_counts={'instagram:123':1};
fixtures.social_commands=[{id:actionId,channel:'instagram',external_id:'123',account_scope:'current'}];
let inboxProgress=await server.loadSocialSnapshot(modelId) as {people:{contacts:{replyInProgress:boolean;waitingMessageCount:number}[]}[]};
assert.equal(inboxProgress.people[0].contacts[0].replyInProgress,true);
assert.equal(inboxProgress.people[0].contacts[0].waitingMessageCount,1,'Sending must not mutate the authoritative waiting count');
assert.ok(calls.some(c=>c.table==='social_commands' && c.method==='eq' && c.args[0]==='model_id' && c.args[1]===modelId));
assert.ok(calls.some(c=>c.table==='social_commands' && c.method==='neq' && c.args[0]==='operation' && c.args[1]==='regenerate'));
assert.ok(calls.some(c=>c.table==='social_commands' && c.method==='in' && c.args[0]==='status' && JSON.stringify(c.args[1])==='["queued","working","sending"]'));
fixtures.social_commands=[{id:actionId,channel:'instagram',external_id:'123',account_scope:'old-account'}];
inboxProgress=await server.loadSocialSnapshot(modelId) as typeof inboxProgress;
assert.equal(inboxProgress.people[0].contacts[0].replyInProgress,false,'An old connected account cannot light the current account');
fixtures.social_commands=[];
inboxProgress=await server.loadSocialSnapshot(modelId) as typeof inboxProgress;
assert.equal(inboxProgress.people[0].contacts[0].replyInProgress,false,'Terminal failure or success ends the spinner; existing waiting count stays authoritative');
console.log('PASS: owner-scoped durable inbox send progress, preserved counts and reconnect isolation');

reset();
fixtures.social_contact_summaries={channel:'instagram',external_id:'123',account_scope:'current',last_message_id:'42'};
fixtures.persona={cta_link:'https://fanvue.com/model'};
fixtures.instagram={bio_link:'https://linkovne.com/model',telegram_handle:'model_user',funnel_target:'both'};
const sitesThread=await server.loadSocialThread(modelId,'instagram:123') as {sites:{label:string;url:string;available:boolean}[]};
assert.deepEqual(sitesThread.sites.map(s=>[s.label,s.available]),[['Fanvue',true],['Linkovne',true],['Telegram',true]]);
for(const table of ['persona','instagram'])assert.ok(calls.some(c=>c.table===table&&c.method==='eq'&&c.args[0]==='model_id'&&c.args[1]===modelId));
assert.ok(calls.some(c=>c.table==='instagram'&&c.method==='select'&&c.args[0]==='bio_link,telegram_handle,funnel_target'),'Site picker never selects access tokens');
console.log('PASS: model-configured link DTO and channel restrictions');

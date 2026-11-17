import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import * as policy from '../lib/social-brief-policy.ts';
import {SocialError} from '../lib/social-policy.ts';
const require=createRequire(import.meta.url);
let aiCalls=0,bills=0,claims=0,allowed=true,credit=true,fail=false,changed=false,release=0;
let row:Record<string,unknown>|null=null;
const a={key:'instagram:1',channel:'instagram',externalId:'1',accountScope:'scope',identityId:'i',identityUpdatedAt:'v1',displayName:'Person',username:'person',summary:'Historical fact',personId:null};
const db={from(table:string){let updating=false;let patch:Record<string,unknown>={};const q=new Proxy({},{get(_,method:string){
 if(method==='then')return (done:(v:unknown)=>void)=>{
   if(table==='social_person_briefs'){
    if(updating){row={...row,...patch};if(!patch.summary)release++;}
    return done({data:row,error:null});
   }
   if(table==='ig_messages')return done({data:[{id:'1',role:'user',content:'hello',occurred_at:'2026-11-16T00:00:00Z'}],count:1,error:null});
   return done({data:[],error:null});
 };
 return (...args:unknown[])=>{if(method==='update'){updating=true;patch=args[0] as Record<string,unknown>;}return q;};
}});return q;},async rpc(name:string){if(name==='credit_state')return {data:[{balance:credit?1:0,unlimited:false}],error:null};
 claims++;if(row?.lease_until && Date.parse(String(row.lease_until))>Date.now())return {data:{claimed:false,item:row},error:null};
 row={...row,lease_token:'lease',lease_until:new Date(Date.now()+600000).toISOString()};return {data:{claimed:true,item:row},error:null};}};
const mocks:Record<string,unknown>={
 'server-only':{},'node:crypto':require('node:crypto'),
 '@/lib/social-server':{socialContext:async()=>{if(!allowed)throw new SocialError('Denied',403);return {model:{id:'m'},userId:'owner',channels:['instagram'],db};},socialContact:async()=>({...a,identityUpdatedAt:changed?'v2':'v1'}),CONTACT_COLUMNS:'id'},
 '@/lib/social-policy':{SocialError,mapSocialContact:(r:unknown)=>r},'@/lib/social-brief-policy':policy,
 '@/lib/llm':{llmConfigured:()=>true,llmModel:()=> 'existing-model',parseJsonish:JSON.parse,chatJson:async()=>{aiCalls++;if(fail)return {ok:false,error:'Provider offline',usage:{input:1,output:0}};return {ok:true,content:JSON.stringify({summary:'Known facts and recent topic'}),usage:{input:4,output:2}};}},
 '@/lib/credits':{OUT_OF_CREDITS_MSG:'No credit',recordUsage:async()=>{bills++;}},
};
const code=ts.transpileModule(readFileSync(new URL('../lib/social-brief-server.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};vm.runInThisContext(`(function(require,module,exports){${code}\n})`)((n:string)=>mocks[n]??require(n),mod,mod.exports);
const server=mod.exports as {personBrief:(model:string,key:string,refresh?:boolean)=>Promise<{brief:{summary:string;generating:boolean}}>};
allowed=false;await assert.rejects(server.personBrief('m',a.key),/Denied/);assert.equal(aiCalls,0);allowed=true;
const first=await server.personBrief('m',a.key);assert.match(first.brief.summary,/Known facts/);assert.equal(aiCalls,1);assert.equal(bills,1);
credit=false;await server.personBrief('m',a.key);assert.equal(aiCalls,1);credit=true;
row={...(row as Record<string,unknown>|null),lease_until:new Date(Date.now()+600000).toISOString()};const busy=await server.personBrief('m',a.key,true);assert.equal(busy.brief.generating,true);assert.equal(aiCalls,1);
row={...(row as Record<string,unknown>|null),lease_until:null};fail=true;await assert.rejects(server.personBrief('m',a.key,true),/Provider offline/);assert.equal(row?.summary,'Known facts and recent topic');assert.equal(bills,2);assert.equal(release,1);
row=null;credit=false;await assert.rejects(server.personBrief('m',a.key),/No credit/);assert.equal(aiCalls,2);
credit=true;fail=false;
// The provider completes after membership changed: no private brief may be published.
(mocks['@/lib/llm'] as {chatJson:()=>Promise<unknown>}).chatJson=async()=>{changed=true;return {ok:true,content:JSON.stringify({summary:'must not publish'}),usage:{input:1,output:1}};};
// Re-transpile bindings are property accesses, so the current provider mock is used.
await assert.rejects(server.personBrief('m',a.key),/Linked accounts changed/);assert.notEqual((row as Record<string,unknown>|null)?.summary,'must not publish');
assert(claims>=3);console.log('PASS: summary auth, cache, credits, single-flight, billing, failure retention and identity recheck');

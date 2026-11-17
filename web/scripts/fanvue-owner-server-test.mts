import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';import {createRequire} from 'node:module';import vm from 'node:vm';import ts from 'typescript';
import {SocialError} from '../lib/social-policy.ts';import * as policy from '../lib/fanvue-owner-policy.ts';
const require=createRequire(import.meta.url);let allowed=true;let row:Record<string,unknown>|null=null;let inserts=0;const filters:string[]=[];
const db={from(table:string){let insertion:Record<string,unknown>|null=null;let count=false;const q=new Proxy({},{get(_,method:string){if(method==='then')return(done:(r:unknown)=>void)=>{
 if(table==='fanvue')return done({data:{connected:true,creator_uuid:'creator'},error:null});
 if(insertion){inserts++;row={...insertion,input:JSON.parse(JSON.stringify(insertion.input)),expires_at:new Date(Date.now()+86400000).toISOString(),status:'queued',output:{},error:''};}
 return done({data:count?null:row,count:0,error:null});};
 return(...args:unknown[])=>{if(method==='insert')insertion=args[0] as Record<string,unknown>;if(method==='select'&&(args[1] as {head?:boolean})?.head)count=true;if(method==='gt')filters.push(String(args[0]));return q;};}});return q;}};
const mocks:Record<string,unknown>={'server-only':{},'@/lib/social-server':{socialContext:async()=>{if(!allowed)throw new SocialError('Denied',403);return {model:{id:'model'},db};},requireSocialChannel(){}},'@/lib/social-policy':{SocialError},'@/lib/fanvue-owner-policy':policy};
const source=ts.transpileModule(readFileSync(new URL('../lib/fanvue-owner-server.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;const mod={exports:{}};vm.runInThisContext(`(function(require,module,exports){${source}\n})`)((name:string)=>mocks[name]??require(name),mod,mod.exports);
const server=mod.exports as {ownerMediaRequest:(m:string,s:string,i:unknown)=>Promise<unknown>};const request={id:'11111111-1111-4111-8111-111111111111',action:'list',page:1,folder:'Photos'};
allowed=false;await assert.rejects(server.ownerMediaRequest('model','fanvue:creator',request),/Denied/);assert.equal(inserts,0);allowed=true;
await assert.rejects(server.ownerMediaRequest('model','fanvue:foreign',request),/connection changed/);assert.equal(inserts,0);
await server.ownerMediaRequest('model','fanvue:creator',request);assert.equal(inserts,1);assert(filters.includes('expires_at'));
(row as unknown as Record<string,unknown>).input={folder:'Photos',page:1};await server.ownerMediaRequest('model','fanvue:creator',request);assert.equal(inserts,1);
(row as unknown as Record<string,unknown>).expires_at='2000-01-01';await assert.rejects(server.ownerMediaRequest('model','fanvue:creator',request),/expired/);
console.log('PASS: owner media auth, account scope, JSONB replay order, expiry and bounded job creation');

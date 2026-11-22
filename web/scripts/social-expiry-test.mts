/* eslint-disable @typescript-eslint/no-explicit-any -- Isolated VM fixtures model untyped JSX trees and mocked module exports. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as state from '../components/app/social/state.ts';
const source=readFileSync(new URL('../components/app/social/conversation.tsx',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const now=Date.parse('2026-11-22T14:00:00Z');
const contact={key:'instagram:fan',channel:'instagram',externalId:'fan',username:'gary.boone9',displayName:'Gary',accountScope:'account',lastMessageId:'42',identityId:null,identityUpdatedAt:null};
let copied:string[]=[];let commands:any[]=[];let updates:any[]=[];
function render(expired:boolean){
 copied=[];commands=[];updates=[];
 const thread={contact,messages:[{id:'42',channel:'instagram',role:'user',content:'Are you there?',occurredAt:expired?'2026-11-18T18:06:00Z':'2026-11-22T13:59:00Z'}],commands:expired?[{id:'failed',operation:'approve',channel:'instagram',externalId:'fan',status:'blocked',reason:'window_expired',text:'my previously selected reply',createdAt:'2026-11-22T13:00:00Z',deliveryState:null}]:[],pending:{id:'pending',updatedAt:'now',suggestions:['hello there']},linkedContacts:[]};
 const draft={text:'my own reply',brief:'say hi in your style',submitting:false,retry:null,activity:null,error:'',notice:''};
 const transport={submitSocialCommand:async(_model:string,input:any)=>{commands.push(input);return {command:{id:'queued',status:'queued'}}},skipSocialPending:async()=>({})};
 const jsx=(type:any,props:any)=>({type,props});
 const noop=()=>null;
 const mocks:Record<string,any>={
  'react':{useEffect(){},useRef:(value:any)=>({current:value}),useState:(value:any)=>[value,()=>{}]},
  'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},
  'lucide-react':new Proxy({},{get:()=>noop}),
  './transport':{useSocialTransport:()=>({transport,mini:true})},
  '@/lib/utils':{cn:(...v:any[])=>v.filter(Boolean).join(' ')},
  './state':state,
  './use-resource':{useSocialResource:()=>({data:thread,error:null,loading:false,refresh:async()=>thread,update(){}})},
 };
 for(const [path,name] of [['voice-reply','VoiceReply'],['person-brief','PersonBrief'],['fanvue-attachments','FanvueAttachments'],['sites-picker','SitesPicker'],['person-panel','PersonPanel'],['message-media','MessageMedia']])mocks['./'+path]={[name]:noop};
 const mod={exports:{}};
 const context=vm.createContext({module:mod,exports:mod.exports,require:(name:string)=>{assert.ok(name in mocks,name);return mocks[name]},URLSearchParams,AbortController,crypto,Date:class extends Date{static now(){return now}},navigator:{clipboard:{writeText:async(text:string)=>{copied.push(text)}}}});
 vm.runInContext(compiled,context);
 return (mod.exports as any).Conversation({modelId:'model',contact,channelState:{available:true,connected:true,mode:'semi'},draft,updateDraft:(_key:string,fn:any)=>updates.push(fn(draft)),selectContact(){},refreshInbox(){}});
}
function all(node:any):any[]{if(!node||typeof node!=='object')return [];return [node,...[node.props?.children].flat(Infinity).flatMap(all)]}
const settle=async()=>{await new Promise(resolve=>setTimeout(resolve,0))};
let nodes=all(render(true));
assert.ok(nodes.some(n=>n.props?.role==='status'&&JSON.stringify(n).includes('24-hour')));
const unsentCopy=nodes.find(n=>n.type==='button'&&JSON.stringify(n).includes('Copy unsent reply'));
assert.ok(unsentCopy);await unsentCopy.props.onClick();await settle();assert.deepEqual(copied,['my previously selected reply']);assert.equal(commands.length,0);copied=[];
const copy=nodes.find(n=>n.type==='button'&&n.props['aria-label']==='Copy reply 1');
assert.ok(copy&&!copy.props.disabled);
await copy.props.onClick();await settle();assert.deepEqual(copied,['hello there']);assert.equal(commands.length,0);
const compose=nodes.find(n=>n.type==='form'&&n.props.className.includes('social-exact-composer'));
const manualSend=all(compose).find(n=>n.type==='button'&&n.props.type==='submit');assert.equal(manualSend.props.disabled,true);assert.ok(JSON.stringify(manualSend).includes('Send'));assert.ok(!JSON.stringify(manualSend).includes('Copy'));
compose.props.onSubmit({preventDefault(){}});await settle();assert.deepEqual(copied,['hello there']);assert.equal(commands.length,0);
const manualCopy=all(compose).find(n=>n.type==='button'&&JSON.stringify(n).includes('Copy for Instagram'));assert.ok(manualCopy&&!manualCopy.props.disabled);await manualCopy.props.onClick();assert.deepEqual(copied,['hello there','my own reply']);
const say=nodes.find(n=>n.type==='form'&&n!==compose);
say.props.onSubmit({preventDefault(){}});await settle();assert.equal(commands.length,1);assert.equal(commands[0].operation,'regenerate');assert.equal(commands[0].brief,'say hi in your style');
assert.ok(nodes.some(n=>n.type==='a'&&n.props.href==='https://www.instagram.com/gary.boone9/'));
nodes=all(render(false));assert.ok(!nodes.some(n=>n.type==='button'&&n.props['aria-label']==='Copy reply 1'));
const send=nodes.find(n=>n.type==='button'&&n.props['aria-label']==='Send reply 1');assert.ok(send&&!send.props.disabled);await send.props.onClick();await settle();assert.equal(commands[0].operation,'approve');assert.equal(copied.length,0);
console.log('PASS: actual Conversation expired Send disabled with explicit Copy/native alternative, no hidden copy on submit, Say this works, new inbound restores Send');

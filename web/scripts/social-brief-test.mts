import assert from 'node:assert/strict';
import { briefKey, briefContext, parseBrief } from '../lib/social-brief-policy.ts';
const a={channel:'instagram',externalId:'1',accountScope:'s',identityId:'a',identityUpdatedAt:'v1'};
const b={...a,channel:'telegram',externalId:'2'};
assert.equal(briefKey([a,b]),briefKey([b,a]));
assert.notEqual(briefKey([a,b]),briefKey([a]));
assert.notEqual(briefKey([a]),briefKey([{...a,accountScope:'other'}]));
assert.notEqual(briefKey([a]),briefKey([{...a,identityUpdatedAt:'v2'}]));
assert.throws(()=>parseBrief({summary:''}));
assert.equal(parseBrief({summary:'Known facts\nRecent context'}),'Known facts\nRecent context');
const c=briefContext([{account:'instagram @a',memory:'old facts',rows:[{id:'2',role:'assistant',content:'newer',at:'2026-11-17T00:00:00Z'},{id:'1',role:'user',content:'hello',at:'2026-11-16T00:00:00Z'}],total:2}]);
assert(c.text.indexOf('hello')<c.text.indexOf('newer'));
assert(c.text.includes('old facts'));assert.equal(c.truncated,false);
const cut=briefContext([{account:'telegram',memory:'',rows:[{id:'1',role:'user',content:'a'.repeat(200000),at:''}],total:10}]);
assert(cut.text.length<170000);assert.equal(cut.truncated,true);
console.log('PASS: person brief identity, chronology, coverage and output validation');

const many=briefContext(Array.from({length:12},(_,i)=>({account:`network ${i}`,memory:"m".repeat(6000),rows:[{id:"1",role:"user",content:"t".repeat(2400),at:"2026-11-17"}],total:1})));assert(many.text.length<150000);

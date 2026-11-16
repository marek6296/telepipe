// Local, disposable Postgres-WASM contract test. Never connects to production.
// npm install --prefix /tmp/telepipe-db-test @electric-sql/pglite
// TELEPIPE_PGLITE_MODULE=/tmp/telepipe-db-test/node_modules/@electric-sql/pglite/dist/index.js node scripts/test-conversation-db.mjs
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const { PGlite } = await import(process.env.TELEPIPE_PGLITE_MODULE || '@electric-sql/pglite');
const db = new PGlite();
const read = file => readFile(new URL('../supabase/migrations/' + file, import.meta.url), 'utf8');
try {
  await db.exec(`create role anon; create role authenticated; create role service_role;
    create schema auth; create function auth.uid() returns uuid language sql as 'select null::uuid';
    create table models(id uuid primary key,account_id uuid,status text default 'active');
    create table settings(model_id uuid primary key,ai_paused boolean default false,paused_until timestamptz);
    create table photos(model_id uuid,id bigserial,url text,active boolean default true,spicy boolean default false);
    create table dm_users(model_id uuid,tg_id bigint,username text,first_name text,link_sent_at timestamptz);
    create table fv_users(model_id uuid,fan_uuid text,handle text,display_name text);
    grant select on models to authenticated; grant usage on schema auth to authenticated;`);
  const initial = await read('20260824010000_instagram.sql');
  await db.exec(initial.slice(initial.indexOf('create table'), initial.indexOf('comment on table')));
  const chats = await read('20260824030000_instagram_agent.sql');
  await db.exec(chats.slice(chats.indexOf('create table'), chats.indexOf('comment on table')));
  await db.exec(await read('20261116090354_shared_conversations.sql'));
  const m = '00000000-0000-4000-8000-000000000001';
  const m2 = '00000000-0000-4000-8000-000000000002';
  await db.query(`insert into models(id) values ($1),($2)`,[m,m2]);
  await db.query(`insert into instagram(model_id,connected,enabled,reply_mode,ig_user_id) values($1,true,true,'auto','account')`,[m]);
  await db.query(`insert into ig_users(model_id,igsid,last_source_mid,last_incoming_at,age_state) values($1,'fan','in-1',now(),'adult_self_declared')`,[m]);
  await db.query(`insert into dm_users values($1,999,'legacy','Roberto',now()-interval '1 hour')`,[m]);
  await db.exec(await read('20261116093007_conversation_rollout_controls.sql'));
  const seeded=(await db.query(`select status,last_invite_at from conversation_identities where model_id=$1 and external_id='999'`,[m])).rows[0];
  assert.equal(seeded.status,'local','backfill must not verify a heuristic identity');
  assert.ok(seeded.last_invite_at);
  const rpc = async (fn,args) => (await db.query(`select ${fn}(${args.map((_,i)=>'$'+(i+1)).join(',')}) as result`,args)).rows[0].result;
  const first = await rpc('conversation_ensure_identity',[m,'instagram','fan','account','roberto','Roberto']);
  const again = await rpc('conversation_ensure_identity',[m,'instagram','fan','account','roberto2','Roberto']);
  assert.equal(first.id,again.id);
  assert.equal(again.username,'roberto2');
  const tg = await rpc('conversation_ensure_identity',[m,'telegram','111','primary','rob','Roberto']);
  const recognized = await rpc('conversation_pair',[m,tg.id,first.id,'recognized',{}]);
  assert.equal(recognized.person_id,tg.person_id,'recognition must not merge private memory');
  const verified = await rpc('conversation_pair',[m,tg.id,first.id,'verified',{}]);
  assert.equal(verified.person_id,first.person_id);
  const rejected = await rpc('conversation_pair',[m,tg.id,first.id,'rejected',{}]);
  assert.notEqual(rejected.person_id,first.person_id);
  assert.ok(rejected.rejected_ids.includes(first.id));
  await assert.rejects(rpc('conversation_pair',[m2,tg.id,first.id,'verified',{}]));

  const now = Date.now();
  const args=[m,'test:in-1','dm','fan','thread','in-1',new Date(now-10000),new Date(now-1000),new Date(now+3600000),{account_id:'account'}];
  const action = await rpc('instagram_enqueue',args);
  assert.equal((await rpc('instagram_enqueue',args)).id,action.id,'replayed input deduplicated');
  const claim = await rpc('instagram_claim',[m]);
  assert.equal(claim.id,action.id);
  assert.equal(await rpc('instagram_claim',[m]),null,'leased action cannot be claimed twice');
  assert.equal((await rpc('instagram_reserve',[m,action.id,'00000000-0000-4000-8000-000000000099','hello',false,false])).reason,'stale_lease');
  assert.equal((await rpc('instagram_reserve',[m,action.id,claim.lease_token,'hello',false,false])).ok,true);
  assert.equal(await rpc('instagram_finish',[m,action.id,claim.lease_token,'uncertain','','timeout']),true);
  const uncertain = (await db.query(`select state,reserved_at from instagram_actions where id=$1`,[action.id])).rows[0];
  assert.equal(uncertain.state,'uncertain');
  assert.ok(uncertain.reserved_at,'uncertain delivery retains its budget');
  assert.equal(await rpc('instagram_claim',[m]),null,'uncertain sends never retry blindly');
  await rpc('instagram_finish',[m,action.id,claim.lease_token,'sent','provider-1','reconciled']);

  // Older reserved sends still count when the LA calendar date rolls over.
  await db.query(`update instagram_actions set reserved_at=now()-interval '6 hours',contains_link=true where id=$1`,[action.id]);
  await db.query(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,due_at,expires_at,state,contains_link,reserved_at)
    values($1,'old-link','dm','other','other',now()-interval '11 hours',now()+interval '1 hour','sent',true,now()-interval '10 hours')`,[m]);
  await db.query(`update ig_users set last_source_mid='in-2' where model_id=$1 and igsid='fan'`,[m]);
  await rpc('instagram_enqueue',[m,'test:in-2','dm','fan','thread','in-2',new Date(now-1000),new Date(now-1000),new Date(now+3600000),{account_id:'account'}]);
  const claim2 = await rpc('instagram_claim',[m]);
  const limited = await rpc('instagram_reserve',[m,claim2.id,claim2.lease_token,'https://t.me/example',true,false]);
  assert.equal(limited.ok,false);
  assert.ok(['url_limit','url_already_sent'].includes(limited.reason));
  await db.query(`update instagram_actions set due_at=now()-interval '1 second' where id=$1`,[claim2.id]);
  const claim3=await rpc('instagram_claim',[m]);
  await db.query(`update instagram set reply_mode='off' where model_id=$1`,[m]);
  assert.equal((await rpc('instagram_reserve',[m,claim3.id,claim3.lease_token,'hello',false,false])).reason,'stale_lease');
  assert.equal((await db.query(`select state from instagram_actions where id=$1`,[claim3.id])).rows[0].state,'cancelled');

  await db.query(`update instagram set reply_mode='auto' where model_id=$1`,[m]);
  await db.query(`update ig_users set last_source_mid='in-3' where model_id=$1`,[m]);
  await rpc('instagram_enqueue',[m,'test:in-3','dm','fan','thread','in-3',new Date(now-1000),new Date(now-1000),new Date(now+3600000),{account_id:'wrong-account'}]);
  const wrongAccount=await rpc('instagram_claim',[m]);
  assert.equal((await rpc('instagram_reserve',[m,wrongAccount.id,wrongAccount.lease_token,'hello',false,false])).reason,'account_changed');

  await db.query(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,due_at,expires_at,state,reserved_at)
    select $1,'busy-'||g,'dm','busy-'||g,'thread',now(),now()+interval '1 hour','sent',now()-interval '3 minutes' from generate_series(1,3) g`,[m]);
  await db.query(`update ig_users set last_source_mid='in-4' where model_id=$1`,[m]);
  await rpc('instagram_enqueue',[m,'test:in-4','dm','fan','thread','in-4',new Date(now-1000),new Date(now-1000),new Date(now+3600000),{account_id:'account'}]);
  const busy=await rpc('instagram_claim',[m]);
  assert.equal((await rpc('instagram_reserve',[m,busy.id,busy.lease_token,'hello',false,false])).reason,'active_chats_limit');

  await db.exec('set role authenticated');
  assert.equal((await db.query('select * from conversation_identities')).rows.length,0,'RLS hides other owners');
  await assert.rejects(rpc('instagram_claim',[m]),/permission denied/);
  await assert.rejects(db.query(`update conversation_identities set status='verified'`),/permission denied/);
  await db.exec('reset role');
  console.log('PASS: migration, identity isolation/recognition/merge/reject, replay, claim, fencing, uncertain delivery, rolling URL quota, Off and RLS/RPC grants');
} finally { await db.close(); }

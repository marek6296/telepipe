// Disposable Postgres-WASM test; never connects to production.
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const { PGlite } = await import(process.env.TELEPIPE_PGLITE_MODULE || '@electric-sql/pglite');
const db = new PGlite();
const read = file => readFile(new URL('../supabase/migrations/' + file, import.meta.url), 'utf8');
try {
  await db.exec(`create role anon; create role authenticated; create role service_role;
    create table models(id uuid primary key);`);
  const events=await read('011_fanvue.sql');
  await db.exec(events.slice(events.indexOf('create table fanvue_events ('),events.indexOf('-- (c) Singleton')));
  const fans=await read('012_fv_tables.sql');
  await db.exec(fans.slice(fans.indexOf('create table fv_users ('),fans.indexOf('create index fv_users_tg_idx')));
  await db.exec(fans.slice(fans.indexOf('create table fv_messages ('),fans.indexOf('create index fv_messages_fan_idx')));
  await db.exec(await read('20261116160900_fanvue_deferred_replies.sql'));
  await db.exec(await read('20261116162501_fanvue_pending_thanks.sql'));
  await db.exec('grant select,update on fanvue_events,fv_users to service_role');
  const a='00000000-0000-4000-8000-000000000001',b='00000000-0000-4000-8000-000000000002';
  await db.query('insert into models values($1),($2)',[a,b]);
  await db.query(`insert into fv_users(model_id,fan_uuid,pending_offer_at) values($1,'fan',now()),($2,'fan',now())`,[a,b]);
  await db.query(`insert into fv_messages(model_id,fan_uuid,role,content) values($1,'fan','user','legacy import')`,[a]);
  await db.exec(await read('20261116182921_conversation_message_times.sql'));
  assert.equal((await db.query('select occurred_at from fv_messages')).rows[0].occurred_at,null,'migration must not invent source times from import time');
  await db.query(`insert into fv_messages(model_id,fan_uuid,role,content,occurred_at) values($1,'fan','user','source time','2026-11-15T21:40:00Z')`,[a]);
  assert.equal(new Date((await db.query(`select occurred_at from fv_messages where content='source time'`)).rows[0].occurred_at).toISOString(),'2026-11-15T21:40:00.000Z');
  assert.equal((await db.query('select pending_thanks from fv_users where model_id=$1',[a])).rows[0].pending_thanks,false);
  // Reconciliation must persist the retry in the same update as the observed
  // purchase count; another tenant's identical fan UUID stays untouched.
  await db.query('update fv_users set bought_count=1,pending_thanks=true where model_id=$1 and fan_uuid=$2',[a,'fan']);
  assert.equal((await db.query('select pending_thanks from fv_users where model_id=$1',[a])).rows[0].pending_thanks,true);
  assert.equal((await db.query('select pending_thanks from fv_users where model_id=$1',[b])).rows[0].pending_thanks,false);
  await db.query('update fv_users set bought_count=0,pending_thanks=false where model_id=$1 and fan_uuid=$2',[a,'fan']);
  const event=(await db.query('insert into fanvue_events(model_id) values($1) returning id',[a])).rows[0].id;
  const once=async(model,id,fan,cents)=>(await db.query('select fanvue_record_payment_once($1,$2,$3,$4) as fan',[model,id,fan,cents])).rows[0].fan;
  await db.exec('set role service_role');
  await assert.rejects(once(b,event,'fan',1234),/not found for model/);
  await assert.rejects(once(a,event,'missing',1234),/fan not found/);
  assert.equal((await db.query('select payment_recorded_at from fanvue_events where id=$1',[event])).rows[0].payment_recorded_at,null,'failed transaction must not consume the payment');
  await assert.rejects(once(a,event,'fan',-1),/nonnegative/);
  const first=await once(a,event,'fan',1234);
  assert.equal(first.spent_cents,1234); assert.equal(first.bought_count,1); assert.equal(first.pending_offer_at,null);
  const replay=await once(a,event,'fan',9999);
  assert.equal(replay.spent_cents,1234); assert.equal(replay.bought_count,1,'retrying the thank-you must not repeat accounting');
  assert.equal((await db.query('select spent_cents from fv_users where model_id=$1',[b])).rows[0].spent_cents,0);
  await db.exec('reset role');
  const next=(await db.query('insert into fanvue_events(model_id) values($1) returning id',[a])).rows[0].id;
  assert.equal((await once(a,next,'fan',200)).spent_cents,1434);
  await db.query('update fanvue_events set reply_deferred=true where id=$1',[event]);
  const deferred=(await db.query('select processed_at,notified_at from fanvue_events where id=$1',[event])).rows[0];
  assert.equal(deferred.processed_at,null,'scheduled deferral is still pending');
  assert.equal(deferred.notified_at,null);
  await db.exec('set role authenticated');
  await assert.rejects(once(a,event,'fan',1234),/permission denied/);
  await db.exec('reset role');
  console.log('PASS: actual Fanvue migration, payment replay/rollback, tenant isolation, deferred pending state and service-only RPC');
} catch(error) { console.error(error.message); process.exitCode=1; } finally { await db.close(); }

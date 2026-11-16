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
    create table pending_replies(model_id uuid,channel text,conv_key text,status text default 'awaiting');
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
  await db.exec(await read('20261116101120_identity_change_pending_replies.sql'));
  await db.exec(await read('20261116152955_instagram_destination_budgets.sql'));
  const seeded=(await db.query(`select status,last_invite_at from conversation_identities where model_id=$1 and external_id='999'`,[m])).rows[0];
  assert.equal(seeded.status,'local','backfill must not verify a heuristic identity');
  assert.ok(seeded.last_invite_at);
  const rpc = async (fn,args) => (await db.query(`select ${fn}(${args.map((_,i)=>'$'+(i+1)).join(',')}) as result`,args)).rows[0].result;
  await rpc('instagram_record_manual',[m,'manual-mid','manual-fan',new Date(Date.now()-2*86400000),'hello',false,'account']);
  assert.equal((await db.query(`select state from instagram_actions where dedupe_key='account:manual:manual-mid'`)).rows[0].state,'sent');
  const first = await rpc('conversation_ensure_identity',[m,'instagram','fan','account','roberto','Roberto']);
  const again = await rpc('conversation_ensure_identity',[m,'instagram','fan','account','roberto2','Roberto']);
  assert.equal(first.id,again.id);
  assert.equal(again.username,'roberto2');
  const tg = await rpc('conversation_ensure_identity',[m,'telegram','111','primary','rob','Roberto']);
  const recognized = await rpc('conversation_pair',[m,tg.id,first.id,'recognized',{}]);
  assert.equal(recognized.person_id,tg.person_id,'recognition must not merge private memory');
  const verified = await rpc('conversation_pair',[m,tg.id,first.id,'verified',{}]);
  assert.equal(verified.person_id,first.person_id);
  const fv = await rpc('conversation_ensure_identity',[m,'fanvue','fan-uuid','primary','rob','Roberto']);
  await rpc('conversation_pair',[m,fv.id,first.id,'verified',{}]);
  await db.query(`insert into pending_replies(model_id,channel,conv_key) values
    ($1,'telegram','111'),($1,'instagram','fan:approval-id'),($1,'fanvue','fan-uuid'),($1,'telegram','unrelated'),($2,'telegram','111')`,[m,m2]);
  const rejected = await rpc('conversation_pair',[m,tg.id,first.id,'rejected',{}]);
  assert.notEqual(rejected.person_id,first.person_id);
  assert.ok(rejected.rejected_ids.includes(first.id));
  const pending=(await db.query(`select model_id,channel,conv_key,status from pending_replies`)).rows;
  assert.equal(pending.find(r=>r.model_id===m && r.conv_key==='111').status,'superseded','identity rejection invalidates Telegram proposals containing old shared context');
  assert.equal(pending.find(r=>r.channel==='instagram').status,'superseded','the other side of the rejected association also loses stale proposals');
  assert.equal(pending.find(r=>r.channel==='fanvue').status,'superseded','Fanvue proposals must be regenerated too');
  assert.equal(pending.find(r=>r.conv_key==='unrelated').status,'awaiting');
  assert.equal(pending.find(r=>r.model_id===m2).status,'awaiting','another model stays isolated');
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

  // Photo eligibility and reactive consent are checked in the real reservation function.
  await db.query(`insert into instagram(model_id,connected,enabled,reply_mode,ig_user_id,photos_enabled) values($1,true,true,'auto','account2',true)`,[m2]);
  await db.query(`insert into ig_users(model_id,igsid,last_source_mid,last_incoming_at,age_state) values($1,'p2','photo-input',now(),'adult_self_declared')`,[m2]);
  const p2=await rpc('conversation_ensure_identity',[m2,'instagram','p2','account2','test','Test']);
  await db.query(`update conversation_people set age_state='minor_or_conflicting' where model_id=$1 and id=$2`,[m2,p2.person_id]);
  const photo=(await db.query(`insert into photos(model_id,url,instagram_approved) values($1,'https://example.test/sfw.jpg',true) returning id`,[m2])).rows[0];
  await rpc('instagram_enqueue',[m2,'photo-input','photo','p2','thread','photo-input',new Date(now-1000),new Date(now-1000),new Date(now+3600000),{account_id:'account2',photo_id:String(photo.id),photo_url:'https://example.test/sfw.jpg'}]);
  const photoClaim=await rpc('instagram_claim',[m2]);
  assert.equal((await rpc('instagram_reserve',[m2,photoClaim.id,photoClaim.lease_token,'',false,false])).reason,'photo_not_allowed');
  await db.query(`update conversation_people set age_state='adult_self_declared',no_initiate=true,no_links=true,stopped_at=now()-interval '2 hours' where model_id=$1 and id=$2`,[m2,p2.person_id]);
  await db.query(`update ig_users set no_initiate=true,last_source_mid='new-question' where model_id=$1`,[m2]);
  await rpc('instagram_enqueue',[m2,'new-question','dm','p2','thread','new-question',new Date(now-1000),new Date(now-1000),new Date(now+3600000),{account_id:'account2',requested_reply:true}]);
  const question=await rpc('instagram_claim',[m2]);
  assert.equal((await rpc('instagram_reserve',[m2,question.id,question.lease_token,'fine thanks',false,false])).ok,true,'a new explicit question can receive a plain answer after opt-out');
  await db.query(`update ig_users set last_source_mid='new-promo' where model_id=$1`,[m2]);
  await rpc('instagram_enqueue',[m2,'new-promo','dm','p2','thread','new-promo',new Date(now-1000),new Date(now-1000),new Date(now+3600000),{account_id:'account2',requested_reply:true}]);
  const promo=await rpc('instagram_claim',[m2]);
  assert.equal((await rpc('instagram_reserve',[m2,promo.id,promo.lease_token,'https://t.me/example',true,false])).reason,'contact_opt_out','a new question does not renew marketing consent');

  // Destination-specific budgets share the account cap and lifetime recipient guard.
  let caseNo=10;
  async function linkCase(prior, target='telegram', options={}) {
    const id='00000000-0000-4000-8000-'+String(caseNo++).padStart(12,'0');
    await db.query('insert into models(id) values($1)',[id]);
    await db.query(`insert into instagram(model_id,connected,enabled,reply_mode,ig_user_id,funnel_target,telegram_handle,bio_link)
      values($1,true,true,'auto','acct','both','simapussina','https://linkovne.com/simonakralova')`,[id]);
    await db.query(`insert into ig_users(model_id,igsid,last_source_mid,last_incoming_at,age_state)
      values($1,'recipient','source',now(),'adult_self_declared')`,[id]);
    const urls={telegram:'https://t.me/simapussina',bio_link:'https://linkovne.com/simonakralova',unknown:'https://other.test/page'};
    for (let i=0;i<prior.length;i++) {
      const [kind,hours]=prior[i];
      await db.query(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,due_at,expires_at,state,text,contains_link,reserved_at)
        values($1,$2,'dm',$3,'thread',now(),now()+interval '1 hour','sent',$4,true,now()-$5::double precision*interval '1 hour')`,
        [id,'prior'+i,options.samePerson?'recipient':'past'+i,urls[kind],hours]);
    }
    const action=await rpc('instagram_enqueue',[id,'new','dm','recipient','thread','source',new Date(Date.now()-1000),new Date(Date.now()-1000),new Date(Date.now()+3600000),{account_id:'acct'}]);
    if(options.mode) await db.query('update instagram set funnel_target=$2 where model_id=$1',[id,options.mode]);
    const claimed=await rpc('instagram_claim',[id]);
    const result=await rpc('instagram_reserve',[id,action.id,claimed.lease_token,options.url||urls[target],options.flag!==false,false]);
    return result;
  }
  assert.equal((await linkCase([['bio_link',5],['bio_link',10]])).ok,true,'Linkovne quota does not consume Telegram quota');
  assert.equal((await linkCase([['telegram',3],['telegram',6],['telegram',9]])).ok,true,'fourth Telegram URL fits');
  assert.equal((await linkCase([['telegram',3],['telegram',6],['telegram',9],['telegram',12]])).reason,'url_limit');
  assert.equal((await linkCase([['bio_link',5],['bio_link',10]],'bio_link')).reason,'url_limit');
  assert.equal((await linkCase([['telegram',1.5]])).reason,'url_limit');
  assert.equal((await linkCase([['bio_link',3]],'bio_link')).reason,'url_limit');
  assert.equal((await linkCase([['telegram',.5]],'bio_link')).reason,'url_global_limit');
  assert.equal((await linkCase([['unknown',5],['unknown',10]],'bio_link')).reason,'url_limit');
  assert.equal((await linkCase([['telegram',25]],'bio_link',{samePerson:true})).reason,'url_already_sent','another destination is not a repeat-link loophole');
  assert.equal((await linkCase([],'telegram',{mode:'bio_link'})).reason,'link_target_unavailable');
  assert.equal((await linkCase([],'telegram',{url:'https://t.me/simapussina.evil'})).reason,'link_target_unavailable');
  assert.equal((await linkCase([],'telegram',{flag:false})).reason,'unmarked_url');

  await db.exec('set role authenticated');
  assert.equal((await db.query('select * from conversation_identities')).rows.length,0,'RLS hides other owners');
  await assert.rejects(rpc('instagram_claim',[m]),/permission denied/);
  await assert.rejects(db.query(`update conversation_identities set status='verified'`),/permission denied/);
  await db.exec('reset role');
  console.log('PASS: migration, identity isolation/recognition/merge/reject, replay, claim, fencing, uncertain delivery, rolling URL quota, Off and RLS/RPC grants');
} catch (error) { console.error(error.message); process.exitCode=1; } finally { await db.close(); }

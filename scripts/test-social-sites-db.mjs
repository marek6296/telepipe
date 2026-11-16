// Disposable actual-Postgres contracts. Never contacts Supabase or providers.
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const { PGlite } = await import(process.env.TELEPIPE_PGLITE_MODULE || '@electric-sql/pglite');
const db = new PGlite();
const read = name => readFile(new URL('../supabase/migrations/'+name, import.meta.url),'utf8');
const rpc = async (name,args) => (await db.query(`select ${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) as result`, args)).rows[0].result;
const one = async (sql,args=[]) => (await db.query(sql,args)).rows[0];
const m=randomUUID(), other=randomUUID(), owner=randomUUID(), foreignOwner=randomUUID();
try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth; create function auth.uid() returns uuid language sql as 'select null::uuid';
    create table accounts(id uuid primary key,role text default 'user');
    create table models(id uuid primary key,account_id uuid,status text default 'active',model_type text default 'persona',claimed_by text,heartbeat_at timestamptz,tg_session_enc text default '');
    create table settings(model_id uuid primary key,ai_paused boolean default false,paused_until timestamptz,flood_until timestamptz,tg_reply_mode text default 'auto');
    create table fanvue(model_id uuid primary key,enabled boolean default true,reply_mode text default 'auto',creator_uuid text default '');
    create table photos(model_id uuid,id bigserial,url text,active boolean default true,spicy boolean default false);
    grant select on models to authenticated; grant usage on schema auth to authenticated;`);
  const tg=await read('003_tenant_tables.sql');
  await db.exec(tg.slice(tg.indexOf('create table dm_users ('),tg.indexOf('-- Append-only fakty')));
  const fv=await read('012_fv_tables.sql');
  await db.exec(fv.slice(fv.indexOf('create table fv_users ('),fv.indexOf('-- (c) fv_folders')));
  const pending=await read('20260818140000_semi_auto_reply_mode.sql');
  await db.exec(pending.slice(pending.indexOf('create table pending_replies ('),pending.indexOf('-- ===========================================================================',pending.indexOf('create table pending_replies ('))));
  await db.exec(`alter table pending_replies drop constraint pending_replies_channel_check;
    alter table pending_replies add constraint pending_replies_channel_check check(channel in ('telegram','fanvue','instagram'));
    alter table pending_replies add column hint text default '',add column prompt text default '';`);
  for(const name of ['20260824010000_instagram.sql','20260824030000_instagram_agent.sql']) {
    const sql=await read(name); await db.exec(sql.slice(sql.indexOf('create table'),sql.indexOf('comment on table')));
  }
  for(const name of ['20261116090354_shared_conversations.sql','20261116093007_conversation_rollout_controls.sql',
    '20261116101120_identity_change_pending_replies.sql','20261116152955_instagram_destination_budgets.sql',
    '20261116154902_instagram_unanswered_recovery.sql','20261116182921_conversation_message_times.sql',
    '20261116220950_social_sites_inbox.sql','20261116223529_social_instagram_suggestion_previews.sql']) await db.exec(await read(name));
  assert.ok((await one("select to_regclass('public.social_commands') as table_name")).table_name,'durable social queue must exist');
  await db.query(`insert into accounts(id) values($1),($2)`,[owner,foreignOwner]);
  await db.query(`insert into models(id,account_id,claimed_by,heartbeat_at) values($1,$2,'worker-a',now()),($3,$4,'worker-b',now())`,[m,owner,other,foreignOwner]);
  await db.query(`insert into settings(model_id) values($1),($2)`,[m,other]);
  await db.query(`insert into dm_users(model_id,tg_id,first_name) values($1,101,'Alice'),($1,102,'Bob'),($2,101,'Foreign')`,[m,other]);
  await db.query(`insert into fv_users(model_id,fan_uuid,display_name) values($1,'fan-a','Alice Fanvue')`,[m]);
  await db.query(`insert into dm_messages(model_id,tg_id,role,content,created_at) values($1,101,'user','Hi Alice',now()),($1,102,'user','Hi Bob',now()-interval '1 hour'),($2,101,'user','private',now())`,[m,other]);
  await db.query(`insert into fv_messages(model_id,fan_uuid,role,content) values($1,'fan-a','user','unknown source time')`,[m]);
  const identity=await rpc('conversation_ensure_identity',[m,'telegram','101','primary','alice','Alice']);
  const repeated=await rpc('conversation_ensure_identity',[m,'telegram','101','primary','alice','Alice']);
  assert.equal(repeated.updated_at,identity.updated_at,'unchanged observation must not invalidate commands');
  const fan=await rpc('conversation_ensure_identity',[m,'fanvue','fan-a','primary','','Alice Fanvue']);
  await rpc('conversation_pair',[m,fan.id,identity.id,'verified',{}]);
  let page=await rpc('social_inbox',[m,'','', 'all',1,0,false]);
  assert.equal(page.total,2); assert.equal(page.contacts.length,2,'page limit counts people, includes all their accounts');
  assert.ok(page.contacts.every(c=>c.model_id===m));
  const search=await rpc('social_inbox',[m,'Alice Fanvue','','all',50,0,false]);
  assert.equal(search.total,1); assert.equal(search.contacts.length,2,'search one account includes linked siblings');
  const filtered=await rpc('social_inbox',[m,'','fanvue','all',10,0,false]);
  assert.equal(filtered.contacts.length,2,'channel filter selects a person and retains visible linked accounts');
  const second=await rpc('social_inbox',[m,'','','all',1,1,false]);
  assert.equal(second.contacts[0].external_id,'102');
  assert.equal(search.contacts.find(c=>c.channel==='fanvue').last_message_at,null,'unknown source timestamps stay unknown');
  await db.query("update settings set tg_reply_mode='off' where model_id=$1",[m]);
  const manual=await rpc('social_inbox',[m,'','','manual',50,0,false]);
  assert.equal(manual.total,2,'Manual includes globally Off channels even before per-contact takeover');
  await db.query("update settings set tg_reply_mode='auto' where model_id=$1",[m]);
  await db.query(`insert into fv_messages(model_id,fan_uuid,role,content,occurred_at) values
    ($1,'fan-a','user','newer source','2026-11-15T12:00:00Z'),($1,'fan-a','assistant','older imported last','2026-11-14T12:00:00Z')`,[m]);
  const chronological=await one("select last_message_text,last_message_at from social_contact_summaries where model_id=$1 and channel='fanvue'",[m]);
  assert.equal(chronological.last_message_text,'newer source','latest message follows provider time, not import order');
  assert.equal(new Date(chronological.last_message_at).toISOString(),'2026-11-15T12:00:00.000Z');
  const summary=async(channel='telegram',external='101')=>one('select * from social_contact_summaries where model_id=$1 and channel=$2 and external_id=$3',[m,channel,external]);
  const enqueue=async(overrides={})=>{
    const c=await summary(overrides.channel||'telegram',overrides.external||'101');
    const p={key:randomUUID(),operation:'send_text',channel:'telegram',external:'101',scope:c?.account_scope||'primary',pending:null,suggestions:null,source:c?.last_message_id??null,identity:c?.identity_id??null,version:c?.identity_updated_at??null,text:'Exact reply',brief:'',...overrides};
    return rpc('social_enqueue',[m,owner,p.key,p.operation,p.channel,p.external,p.scope,p.pending,p.suggestions,p.source,p.identity,p.version,p.text,p.brief]);
  };
  const key=randomUUID(); const command=await enqueue({key});
  await assert.rejects(db.query("update social_commands set text='mutated' where id=$1",[command.id]),/immutable/);
  assert.equal((await enqueue({key})).id,command.id,'HTTP retry must reuse immutable intent');
  await assert.rejects(enqueue({key,text:'different'}),/idempotency/);
  await assert.rejects(rpc('social_enqueue',[other,owner,randomUUID(),'send_text','telegram','101','primary',null,null,null,null,null,'leak','']),/owner/);
  assert.equal(await rpc('social_claim',[m,'worker-b']),null,'foreign worker must not claim');
  const claimed=await rpc('social_claim',[m,'worker-a']); assert.equal(claimed.id,command.id);
  await enqueue({text:'Next exact reply'});
  assert.equal(await rpc('social_claim',[m,'worker-a']),null,'only one active command per contact');
  const sent=await rpc('social_start_send',[m,claimed.id,claimed.lease_token,'worker-a']); assert.equal(sent.status,'sending');
  await db.query(`update social_commands set lease_until=now()-interval '1 second' where id=$1`,[sent.id]);
  await rpc('social_claim',[m,'worker-a']);
  assert.equal((await one('select status from social_commands where id=$1',[sent.id])).status,'uncertain','expired provider boundary must never retry');
  assert.equal(await rpc('social_finish',[m,sent.id,sent.lease_token,'done',{},'']),false,'late completion is fenced');
  await db.query("update social_commands set status='failed' where model_id=$1 and status in ('queued','working')",[m]);
  for (const crossSendBoundary of [false,true]) {
    const expiredDraft=await one(`insert into pending_replies(model_id,channel,conv_key,suggestions) values($1,'telegram','102','["expired"]') returning id`,[m]);
    const expiredCommand=await enqueue({external:'102',operation:'approve',pending:expiredDraft.id,suggestions:['expired'],text:'expired'});
    const expiredClaim=await rpc('social_claim',[m,'worker-a']);
    if(crossSendBoundary) await rpc('social_start_send',[m,expiredCommand.id,expiredClaim.lease_token,'worker-a']);
    assert.equal(await rpc('social_finish',[m,expiredCommand.id,expiredClaim.lease_token,'blocked',{safe_to_retry:true,restore_pending:false},'window_expired']),true);
    assert.equal((await one('select status from pending_replies where id=$1',[expiredDraft.id])).status,'superseded','a permanently expired action must not revive an unusable draft');
  }
  const stale=await enqueue(); const staleClaim=await rpc('social_claim',[m,'worker-a']);
  await db.query(`insert into dm_messages(model_id,tg_id,role,content) values($1,101,'user','new input')`,[m]);
  assert.equal(await rpc('social_start_send',[m,stale.id,staleClaim.lease_token,'worker-a']),null);
  assert.equal((await one('select status from social_commands where id=$1',[stale.id])).status,'stale');
  const lateImport=await enqueue({channel:'fanvue',external:'fan-a'});
  const lateClaim=await rpc('social_claim',[m,'worker-a']);
  await db.query(`insert into fv_messages(model_id,fan_uuid,role,content) values($1,'fan-a','user','late unknown-time import')`,[m]);
  assert.equal((await summary('fanvue','fan-a')).last_message_text,'newer source','late unknown import does not invent a new provider time');
  assert.equal(await rpc('social_start_send',[m,lateImport.id,lateClaim.lease_token,'worker-a']),null,'any added history invalidates the reviewed context');
  const pendingRow=await one(`insert into pending_replies(model_id,channel,conv_key,suggestions) values($1,'telegram','101','["one","two"]') returning id`,[m]);
  const foreignPending=await one(`insert into pending_replies(model_id,channel,conv_key,suggestions) values($1,'telegram','101','["one"]') returning id`,[other]);
  await assert.rejects(enqueue({operation:'approve',pending:foreignPending.id,suggestions:['one'],text:'one'}),/foreign proposal/);
  const approve=await enqueue({operation:'approve',pending:pendingRow.id,suggestions:['one','two'],text:'one'});
  const approveClaim=await rpc('social_claim',[m,'worker-a']);
  assert.equal(await rpc('social_replace_suggestions',[m,pendingRow.id,['one','two'],['new'],'']),true);
  assert.equal(await rpc('social_start_send',[m,approve.id,approveClaim.lease_token,'worker-a']),null,'changed suggestions invalidate exact approval');
  const approved=await enqueue({operation:'approve',pending:pendingRow.id,suggestions:['new'],text:'new'});
  const approvedClaim=await rpc('social_claim',[m,'worker-a']);
  await rpc('social_start_send',[m,approved.id,approvedClaim.lease_token,'worker-a']);
  assert.equal((await rpc('social_start_send',[m,approved.id,approvedClaim.lease_token,'worker-a'])).id,approved.id,'same lease may recheck an existing send boundary');
  assert.equal(await rpc('social_skip_pending',[m,pendingRow.id,['new']]),false,'skip must not overwrite a sending draft');
  assert.equal((await one('select decision_command_id from pending_replies where id=$1',[pendingRow.id])).decision_command_id,approved.id);
  assert.equal((await db.query("update pending_replies set status='sent' where id=$1 and status='awaiting' returning id",[pendingRow.id])).rows.length,0,'bot cannot claim web-owned proposal');
  assert.equal(await rpc('social_finish',[m,approved.id,approvedClaim.lease_token,'failed',{safe_to_retry:true},'definitely_unsent']),true);
  assert.equal((await one('select status from pending_replies where id=$1',[pendingRow.id])).status,'awaiting','safe failure restores only owned claim');
  const uncertainProposal=await enqueue({operation:'approve',pending:pendingRow.id,suggestions:['new'],text:'new'});
  const uncertainClaim=await rpc('social_claim',[m,'worker-a']);
  await rpc('social_start_send',[m,uncertainProposal.id,uncertainClaim.lease_token,'worker-a']);
  await rpc('social_finish',[m,uncertainProposal.id,uncertainClaim.lease_token,'failed',{},'provider_timeout']);
  assert.equal((await one('select status from social_commands where id=$1',[uncertainProposal.id])).status,'uncertain');
  assert.equal((await one('select status from pending_replies where id=$1',[pendingRow.id])).status,'sent','unproven failure must never revive a claimed draft');
  const targetSending=await enqueue(); const targetClaim=await rpc('social_claim',[m,'worker-a']);
  await rpc('social_start_send',[m,targetSending.id,targetClaim.lease_token,'worker-a']);
  const linkedCommand=await enqueue({channel:'fanvue',external:'fan-a'});
  await rpc('conversation_pair',[m,fan.id,identity.id,'rejected',{}]);
  assert.equal(await rpc('social_start_send',[m,targetSending.id,targetClaim.lease_token,'worker-a']),null,'unlink changes every affected identity version, including the target side already sending');
  assert.equal((await one('select status from social_commands where id=$1',[linkedCommand.id])).status,'stale','identity changes invalidate commands on both sides');
  assert.equal(await rpc('social_set_takeover',[m,'telegram','101',true]),true);
  await db.query('update dm_users set ai_enabled=false where model_id=$1 and tg_id=101',[m]);
  assert.equal(await rpc('social_set_takeover',[m,'telegram','101',false]),true);
  assert.equal((await one('select ai_enabled from dm_users where model_id=$1 and tg_id=101',[m])).ai_enabled,true,'explicit Resume AI restores the per-contact agent switch');
  await rpc('social_set_takeover',[m,'telegram','101',true]);
  assert.equal((await one('select human_takeover from dm_users where model_id=$1 and tg_id=101',[m])).human_takeover,true);
  assert.equal((await one('select human_takeover from dm_users where model_id=$1 and tg_id=101',[other])).human_takeover,false);
  for(const role of ['anon','authenticated']) {
    await db.exec('set role '+role);
    await assert.rejects(rpc('social_inbox',[m,'','','all',10,0,true]),/permission denied/);
    await assert.rejects(db.query('select * from social_commands'),/permission denied/);
    await assert.rejects(rpc('social_set_takeover',[m,'telegram','101',false]),/permission denied/);
    await db.exec('reset role');
  }

  const skip=await one(`insert into pending_replies(model_id,channel,conv_key,suggestions) values($1,'telegram','102','["skip me"]') returning id`,[m]);
  assert.equal(await rpc('social_skip_pending',[other,skip.id,['skip me']]),false,'foreign skip is denied');
  assert.equal(await rpc('social_skip_pending',[m,skip.id,['old']]),false,'stale skip is denied');
  assert.equal(await rpc('social_skip_pending',[m,skip.id,['skip me']]),true);
  assert.equal(await rpc('social_skip_pending',[m,skip.id,['skip me']]),false,'skip decides only once');

  // Reclaim safe work but never trust a worker whose model lease expired.
  const retry=await enqueue({external:'102'}); const retryClaim=await rpc('social_claim',[m,'worker-a']);
  await db.query("update social_commands set lease_until=now()-interval '1 second' where id=$1",[retry.id]);
  const retried=await rpc('social_claim',[m,'worker-a']);
  assert.equal(retried.id,retry.id); assert.notEqual(retried.lease_token,retryClaim.lease_token);
  await db.query("update models set heartbeat_at=now()-interval '91 seconds' where id=$1",[m]);
  assert.equal(await rpc('social_start_send',[m,retried.id,retried.lease_token,'worker-a']),null);
  await db.query('update models set heartbeat_at=now() where id=$1',[m]);
  await rpc('social_finish',[m,retried.id,retried.lease_token,'failed',{},'no_send']);
  const paused=await enqueue({external:'102'}); const pausedClaim=await rpc('social_claim',[m,'worker-a']);
  await db.query('update settings set ai_paused=true where model_id=$1',[m]);
  assert.equal(await rpc('social_start_send',[m,paused.id,pausedClaim.lease_token,'worker-a']),null,'emergency pause is enforced before any channel send boundary');
  await db.query('update settings set ai_paused=false where model_id=$1',[m]);
  const regeneration=await one(`insert into pending_replies(model_id,channel,conv_key,suggestions) values($1,'telegram','102','["old"]') returning id`,[m]);
  const regen=await enqueue({external:'102',operation:'regenerate',pending:regeneration.id,suggestions:['old'],text:''});
  const regenClaim=await rpc('social_claim',[m,'worker-a']);
  await db.query(`insert into dm_messages(model_id,tg_id,role,content) values($1,102,'user','new during LLM')`,[m]);
  assert.equal(await rpc('social_replace_suggestions',[m,regeneration.id,['old'],['obsolete'],'',regen.id,regenClaim.lease_token,'worker-a']),false,'LLM completion must recheck its source atomically');

  // The operator exception must prove command ownership, not trust a payload flag.
  await db.query(`insert into instagram(model_id,connected,enabled,reply_mode,ig_user_id) values($1,true,false,'off','ig-account')`,[m]);
  await db.query(`insert into ig_users(model_id,igsid,last_source_mid,last_incoming_at,human_takeover) values($1,'123','provider-in',now(),true)`,[m]);
  await db.query(`insert into ig_messages(model_id,igsid,mid,role,content,occurred_at) values($1,'123','provider-in','user','hello',now())`,[m]);
  await db.query("update instagram set telegram_handle='example_account',bio_link='https://linkovne.com/example',funnel_target='both' where model_id=$1",[m]);
  assert.deepEqual(await rpc('social_instagram_previews',[m,['[[REMIND]] see you there','check my highlights [[HIGHLIGHTS]]','join me [[TELEGRAM]]','[[LINKPAGE]]','[[PHOTO]]','[[REMIND]] [[LINK]]','[[UNKNOWN]]']]),
    ['see you there','check my highlights','join me https://t.me/example_account','https://linkovne.com/example',null,null,null]);
  const intentDraft=await one(`insert into pending_replies(model_id,channel,conv_key,suggestions) values($1,'instagram','123','["[[REMIND]] see you there"]') returning id`,[m]);
  const canonical=await enqueue({channel:'instagram',external:'123',operation:'approve',pending:intentDraft.id,suggestions:['[[REMIND]] see you there'],text:'see you there'});
  assert.equal(canonical.text,'see you there','the command freezes the exact displayed text, without internal markers');
  await assert.rejects(enqueue({channel:'instagram',external:'123',operation:'approve',pending:intentDraft.id,suggestions:['[[REMIND]] see you there'],text:'changed after review'}),/not a suggestion/);
  await db.query("update social_commands set status='failed' where id=$1",[canonical.id]);
  await db.query("update pending_replies set status='superseded' where id=$1",[intentDraft.id]);
  let ig=await enqueue({channel:'instagram',external:'123',scope:'ig-account',text:'Plain manual answer'});
  let igClaim=await rpc('social_claim',[m,'worker-a']);
  await rpc('social_start_send',[m,ig.id,igClaim.lease_token,'worker-a']);
  let igLease=randomUUID();
  let action=await one(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,source_mid,source_at,due_at,expires_at,state,lease_token,lease_until,payload)
    values($1,'social-operator','dm','123','thread','provider-in',now(),now(),now()+interval '1 hour','leased',$2,now()+interval '2 minutes',$3) returning id`,
    [m,igLease,{origin:'operator',command_id:ig.id,account_id:'ig-account'}]);
  await assert.rejects(db.query(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,due_at,expires_at,payload)
    values($1,'duplicate-operator','dm','123','thread',now(),now()+interval '1 hour',$2)`,[m,{origin:'operator',command_id:ig.id}]),/duplicate/,'one command cannot reserve multiple IG actions');
  await db.query("update instagram set reply_mode='off' where model_id=$1",[m]);
  assert.equal((await one('select state from instagram_actions where id=$1',[action.id])).state,'leased','Off does not cancel an explicit operator action');
  assert.equal((await rpc('instagram_reserve',[m,action.id,igLease,'Plain manual answer',false,false])).ok,true,'Manual bypasses mode and takeover only with a live exact command');
  await rpc('instagram_finish',[m,action.id,igLease,'sent','provider-out','']);
  assert.equal(await rpc('social_finish',[m,ig.id,igClaim.lease_token,'done',{},'']),true);
  const inboxNoIg=await rpc('social_inbox',[m,'','','all',100,0,false]);
  assert.ok(inboxNoIg.contacts.every(c=>c.channel!=='instagram'));
  const inboxIg=await rpc('social_inbox',[m,'','','all',100,0,true]);
  assert.ok(inboxIg.contacts.some(c=>c.channel==='instagram'));
  // Fresh commands still obey source/window, global emergency pause and account budgets.
  async function reserveCase(label,prepare,expected) {
    await db.query("update instagram_actions set reserved_at=now()-interval '2 hours' where model_id=$1",[m]);
    ig=await enqueue({channel:'instagram',external:'123',scope:'ig-account',text:'Another manual answer'});
    igClaim=await rpc('social_claim',[m,'worker-a']);
    await rpc('social_start_send',[m,ig.id,igClaim.lease_token,'worker-a']);
    igLease=randomUUID();
    action=await one(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,source_mid,source_at,due_at,expires_at,state,lease_token,lease_until,payload)
      values($1,$2,'dm','123','thread','provider-in',now(),now(),now()+interval '1 hour','leased',$3,now()+interval '2 minutes',$4) returning id`,
      [m,label,igLease,{origin:'operator',command_id:ig.id,account_id:'ig-account'}]);
    await prepare();
    const result=await rpc('instagram_reserve',[m,action.id,igLease,'Another manual answer',false,false]);
    assert.equal(result.ok,false,label); assert.equal(result.reason,expected,label);
    await rpc('social_finish',[m,ig.id,igClaim.lease_token,'failed',{safe_to_retry:true},expected]);
  }
  await reserveCase('emergency',()=>db.query('update settings set ai_paused=true where model_id=$1',[m]),'global_pause');
  await db.query('update settings set ai_paused=false where model_id=$1',[m]);
  await reserveCase('flood',()=>db.query("update settings set flood_until=now()+interval '1 hour' where model_id=$1",[m]),'global_pause');
  await db.query('update settings set flood_until=null where model_id=$1',[m]);
  await reserveCase('expired-window',()=>db.query("update ig_users set last_incoming_at=now()-interval '25 hours' where model_id=$1",[m]),'window_expired');
  await db.query('update ig_users set last_incoming_at=now() where model_id=$1',[m]);
  await reserveCase('source-changed',()=>db.query("update ig_users set last_source_mid='new-provider-in' where model_id=$1",[m]),'stale_context');
  await db.query("update ig_users set last_source_mid='provider-in' where model_id=$1",[m]);
  await reserveCase('wrong-account',()=>db.query("update instagram_actions set payload=jsonb_set(payload,'{account_id}',to_jsonb('wrong'::text)) where id=$1",[action.id]),'account_changed');
  await reserveCase('quota',()=>db.query(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,due_at,expires_at,state,reserved_at)
    select $1,'quota-'||n,'reaction','other','thread',now(),now()+interval '1 hour','sent',now()-interval '10 minutes' from generate_series(1,20) n`,[m]),'account_limit');
  await db.query("delete from instagram_actions where model_id=$1 and dedupe_key like 'quota-%'",[m]);
  await reserveCase('forged-command',()=>db.query("update instagram_actions set payload=jsonb_set(payload,'{command_id}',to_jsonb($2::text)) where id=$1",[action.id,randomUUID()]),'operator_command_stale');
  const skippedAction=await one(`insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,source_mid,source_at,due_at,expires_at,state)
    values($1,'skipped-source','dm','123','thread','skip-source',now(),now(),now()+interval '1 hour','approval') returning id`,[m]);
  const skippedProposal=await one(`insert into pending_replies(model_id,channel,conv_key,suggestions) values($1,'instagram',$2,'["skip IG"]') returning id`,[m,'123:'+skippedAction.id]);
  assert.equal(await rpc('social_skip_pending',[m,skippedProposal.id,['skip IG']]),true);
  assert.equal((await one('select state from instagram_actions where id=$1',[skippedAction.id])).state,'skipped');
  await db.query("update instagram set reply_mode='auto',enabled=true where model_id=$1",[m]);
  await rpc('instagram_enqueue',[m,'skipped-source','dm','123','thread','skip-source',new Date(Date.now()-1000),new Date(),new Date(Date.now()+3600000),{account_id:'ig-account'}]);
  assert.equal((await one('select state from instagram_actions where id=$1',[skippedAction.id])).state,'skipped','mode recovery never resurrects skipped web approval');
  await rpc('conversation_ensure_identity',[m,'instagram','123','old-account','','']);
  assert.equal((await rpc('social_inbox',[m,'','instagram','all',10,0,true])).contacts.length,0,'an old account identity cannot become a current legacy contact');
  await rpc('conversation_ensure_identity',[m,'instagram','123','ig-account','','']);
  assert.equal((await rpc('social_inbox',[m,'','instagram','all',10,0,true])).contacts.length,1);
  const groupA=await rpc('conversation_ensure_identity',[other,'telegram','201','primary','','']);
  const groupB=await rpc('conversation_ensure_identity',[other,'fanvue','201','primary','','']);
  const groupC=await rpc('conversation_ensure_identity',[other,'telegram','202','primary','','']);
  await rpc('conversation_pair',[other,groupA.id,groupB.id,'verified',{}]);
  await rpc('conversation_pair',[other,groupB.id,groupC.id,'verified',{}]);
  const merged=await db.query('select person_id from conversation_identities where model_id=$1',[other]);
  assert.equal(new Set(merged.rows.map(i=>i.person_id)).size,1,'merging whole linked groups must not trigger recursive row-update failures');
  await db.query("update social_commands set status='failed' where model_id=$1 and status in ('queued','working')",[m]);
  for (const channel of ['telegram','fanvue']) {
    if (channel==='telegram') await db.query("update models set tg_session_enc='session-a' where id=$1",[m]);
    else await db.query("insert into fanvue(model_id,creator_uuid) values($1,'creator-a') on conflict(model_id) do update set creator_uuid='creator-a'",[m]);
    const external=channel==='telegram'?'101':'fan-a';
    const connectedSummary=await summary(channel,external);
    assert.ok(connectedSummary.identity_id,'provider account version must preserve existing primary-scope identity joins');
    const oldAccount=await enqueue({channel,external});
    const oldAccountClaim=await rpc('social_claim',[m,'worker-a']);
    assert.equal(oldAccountClaim.id,oldAccount.id);
    if (channel==='telegram') await db.query("update models set tg_session_enc='session-b' where id=$1",[m]);
    else await db.query("update fanvue set creator_uuid='creator-b' where model_id=$1",[m]);
    assert.equal(await rpc('social_start_send',[m,oldAccount.id,oldAccountClaim.lease_token,'worker-a']),null,'reconnected account cannot execute an old account intent');
    assert.equal((await one('select status from social_commands where id=$1',[oldAccount.id])).status,'stale');
  }
  // Query as the actual intended service role, not only the migration owner.
  await db.exec('grant select on all tables in schema public to service_role; set role service_role');
  assert.equal((await rpc('social_inbox',[m,'','','all',100,0,false])).total,3);
  await db.exec('reset role');
  console.log('PASS social SQL: grouped inbox, isolation/grants, immutable idempotency, leases, draft/source/identity races and safe restore');
} catch(error) { console.error(error.message); process.exitCode=1; } finally { await db.close(); }

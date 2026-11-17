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
  const migration = await read('20261117001000_native_reply_sync.sql');
  if (migration) await db.exec(migration);
  await db.exec("create schema storage; create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[])");
  await db.exec(await read('20261117002000_social_private_message_media.sql'));
  await db.query('insert into accounts(id) values($1)',[owner]);
  await db.query("insert into models(id,account_id,tg_session_enc) values($1,$2,'session')",[m,owner]);
  await db.query("insert into dm_users(model_id,tg_id) values($1,101)",[m]);
  const scope=(await one("select 'telegram:'||md5('session') s")).s;
  const ing=await rpc('social_ingest_telegram',[m,101,1,scope,'user','[voice]',new Date().toISOString(),'native']);
  const claim=await rpc('social_media_claim',[m,'telegram','101',scope,'1','audio','audio']);
  assert.equal(claim.message_id,ing.id);
  assert.equal(claim.status,'processing');
  assert.equal(await rpc('social_media_claim',[m,'telegram','101',scope,'1','audio','audio']),null,'parallel work cannot bill twice');
  assert.equal(await rpc('social_media_claim',[m,'telegram','101','other-account','1','audio','audio']),null);
  assert.equal(await rpc('social_media_claim',[other,'telegram','101',scope,'1','audio','audio']),null);
  const proposal=await one("insert into pending_replies(model_id,channel,conv_key,suggestions,source_message_id) values($1,'telegram','101','[\"old draft\"]',$2) returning id",[m,ing.source_version]);
  const command=await one("insert into social_commands(model_id,requested_by,idempotency_key,operation,channel,external_id,account_scope,expected_source_id,pending_id,expected_suggestions,text,status) values($1,$2,$3,'approve','telegram','101',$4,$5,$6,'[\"old draft\"]','old draft','queued') returning id",[m,owner,randomUUID(),scope,String(ing.source_version),proposal.id]);
  const path=m+'/telegram/'+ing.id+'/'+claim.id+'.mp3';
  const finish={status:'ready',transcript:'The actual words',storage_path:path,mime_type:'audio/mpeg',duration_seconds:4};
  assert.equal(await rpc('social_media_finish',[m,claim.id,randomUUID(),finish]),false);
  await assert.rejects(()=>rpc('social_media_finish',[m,claim.id,claim.lease_token,{...finish,storage_path:other+'/stolen.mp3'}]));
  assert.equal(await rpc('social_media_finish',[m,claim.id,claim.lease_token,finish]),true);
  assert.equal((await one('select status from pending_replies where id=$1',[proposal.id])).status,'superseded');
  assert.equal((await one('select status from social_commands where id=$1',[command.id])).status,'stale','queued approval cannot send placeholder-era draft');
  const message=await one('select * from dm_messages where id=$1',[ing.id]);
  assert.ok(message.content.includes('The actual words'));
  assert.ok(message.context_version>message.id);
  const version=(await one("select last_message_id from social_contact_summaries where model_id=$1 and channel='telegram'",[m])).last_message_id;
  assert.equal(version,String(message.context_version));
  // A serial id is allocated before BEFORE INSERT obtains the model lock.
  // Simulate that reservation, an intervening analysis and a fresh draft.
  const reserved=(await one("select nextval(pg_get_serial_sequence('public.dm_messages','id')) id")).id;
  await db.query("update dm_messages set content=content||E'\\nLater analysis' where id=$1",[ing.id]);
  const afterAnalysis=(await one("select last_message_id from social_contact_summaries where model_id=$1 and channel='telegram'",[m])).last_message_id;
  assert.ok(Number(afterAnalysis)>Number(reserved));
  const racedDraft=await one("insert into pending_replies(model_id,channel,conv_key,suggestions,source_message_id) values($1,'telegram','101','[\"latest draft\"]',$2) returning id",[m,Number(afterAnalysis)]);
  const delayed=await one("insert into dm_messages(id,model_id,tg_id,role,content,created_at) values($1,$2,101,'user','delayed concurrent insert',now()) returning context_version",[reserved,m]);
  assert.ok(delayed.context_version>Number(afterAnalysis),'a preallocated lower message id must still advance context after a concurrent analysis');
  assert.equal((await one('select status from pending_replies where id=$1',[racedDraft.id])).status,'superseded','late commit with reserved lower id invalidates the fresh draft');
  assert.equal(await one("insert into pending_replies(model_id,channel,conv_key,suggestions,source_message_id) values($1,'telegram','101','[]',$2) returning id",[m,ing.id]),undefined,'generation raced with media analysis');
  assert.equal(await rpc('social_media_claim',[m,'telegram','101',scope,'1','audio','audio']),null,'ready media never re-billed');
  const next=await rpc('social_ingest_telegram',[m,101,2,scope,'user','new message',new Date().toISOString(),'native']);
  assert.ok(next.id>message.context_version,'next message advances the same revision sequence');
  const legacy=await one("insert into dm_messages(model_id,tg_id,role,content,created_at) values($1,101,'user','old voice transcript',date_trunc('milliseconds',now()-interval '1 hour')) returning id,created_at",[m]);
  const recovered=await rpc('social_media_claim',[m,'telegram','101',scope,'legacy-ignored','legacy','audio',legacy.created_at,'user']).catch(()=>null);
  assert.equal(recovered,null,'invalid Telegram provider ID cannot mutate history');
  const oldClaim=await rpc('social_media_claim',[m,'telegram','101',scope,'22','legacy','audio',legacy.created_at,'user']);
  assert.equal(oldClaim.message_id,legacy.id,'recent legacy voice binds exact unique timestamp without duplicate message');
  assert.equal(Number((await one('select count(*) n from dm_messages where id=$1',[legacy.id])).n),1);
  const expired=await rpc('social_ingest_telegram',[m,101,31,scope,'user','[old video]',new Date(Date.now()-10*86400000).toISOString(),'native']);
  assert.equal(await rpc('social_media_claim',[m,'telegram','101',scope,'31','old','video']),null);
  assert.equal((await one('select status from social_message_media where message_id=$1',[expired.id])).status,'unavailable');
  await db.query("update models set tg_session_enc='new-account' where id=$1",[m]);
  const newScope=(await one("select 'telegram:'||md5('new-account') s")).s;
  assert.equal(await rpc('social_media_claim',[m,'telegram','101',newScope,'1','collision','audio']),null,'new account provider IDs must never bind old account history');
  assert.equal(await rpc('social_media_finish',[m,oldClaim.id,oldClaim.lease_token,{status:'ready',transcript:'wrong account'}]),false);
  await db.query("update models set tg_session_enc='session' where id=$1",[m]);
  for (const [channel,table,externalColumn,providerColumn,account] of [
    ['fanvue','fv_messages','fan_uuid','message_uuid','fanvue:creator'],
    ['instagram','ig_messages','igsid','mid','ig-account']]) {
    if(channel==='fanvue') {
      await db.query("insert into fanvue(model_id,creator_uuid) values($1,'creator')",[m]);
      await db.query("insert into fv_users(model_id,fan_uuid) values($1,'fan')",[m]);
    } else {
      await db.query("insert into instagram(model_id,ig_user_id) values($1,'ig-account')",[m]);
      await db.query("insert into ig_users(model_id,igsid) values($1,'fan')",[m]);
    }
    const msg=await one(`insert into ${table}(model_id,${externalColumn},${providerColumn},role,content,occurred_at) values($1,'fan','provider','user','[video]',now()) returning id`,[m]);
    const part=await rpc('social_media_claim',[m,channel,'fan',account,'provider','video','video']);
    assert.equal(part.message_id,msg.id);
    assert.equal(await rpc('social_media_finish',[m,part.id,part.lease_token,{status:'ready',transcript:'spoken',description:'visible frame'}]),true);
    const stored=await one(`select * from ${table} where id=$1`,[msg.id]);
    assert.ok(stored.content.includes('spoken') && stored.content.includes('visible frame'));
    const version=(await one('select last_message_id from social_contact_summaries where model_id=$1 and channel=$2',[m,channel])).last_message_id;
    assert.equal(version,String(stored.context_version),channel+' uses semantic revision');
  }
  for(const role of ['anon','authenticated']) {
    assert.equal((await one('select has_table_privilege($1,\'social_message_media\',\'SELECT\') ok',[role])).ok,false);
    assert.equal((await one('select has_function_privilege($1,\'social_media_claim(uuid,text,text,text,text,text,text,timestamptz,text)\',\'EXECUTE\') ok',[role])).ok,false);
  }
  assert.equal((await one("select public from storage.buckets where id='social-media'")).public,false);
  await db.exec(await read('20261117020000_social_waiting_message_counts.sql'));
  await db.query("insert into dm_users(model_id,tg_id) values($1,9999)",[m]);
  const requested=[{channel:'telegram',externalId:'9999',accountScope:scope}];
  const counts=()=>rpc('social_waiting_message_counts',[m,owner,requested]);
  await rpc('social_ingest_telegram',[m,9999,100,scope,'user','one',new Date().toISOString(),'native']);
  await rpc('social_ingest_telegram',[m,9999,101,scope,'user','two',new Date().toISOString(),'native']);
  assert.equal((await counts())['telegram:9999'],2);
  assert.equal((await counts())['telegram:9999'],2,'reading counts never marks a conversation seen');
  await rpc('social_ingest_telegram',[m,9999,99,scope,'assistant','late old reply',new Date(Date.now()-86400000).toISOString(),'native']);
  assert.equal((await counts())['telegram:9999'],2,'old imported reply does not hide newer messages');
  await assert.rejects(()=>rpc('social_waiting_message_counts',[m,foreignOwner,requested]));
  await rpc('social_ingest_telegram',[m,9999,102,scope,'assistant','reply',new Date(Date.now()+1000).toISOString(),'native']);
  assert.equal((await counts())['telegram:9999'],0);
  for(const [channel,table,ext,account] of [['instagram','ig_messages','igsid','ig-account'],['fanvue','fv_messages','fan_uuid','fanvue:creator']]) {
    const list=[{channel,externalId:'fan',accountScope:account}];
    const before=await rpc('social_waiting_message_counts',[m,owner,list]);
    assert.ok(before[channel+':fan']>0);
    await db.query(`insert into ${table}(model_id,${ext},role,content,occurred_at) values($1,'fan','assistant','reply',now()+interval '1 hour')`,[m]);
    assert.equal((await rpc('social_waiting_message_counts',[m,owner,list]))[channel+':fan'],0);
  }
  for(const role of ['anon','authenticated']) assert.equal((await one("select has_function_privilege($1,'social_waiting_message_counts(uuid,uuid,jsonb)','EXECUTE') ok",[role])).ok,false);
  console.log('Private media and semantic source revision SQL contracts passed');
} finally { await db.close(); }

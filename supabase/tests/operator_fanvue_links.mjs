const {PGlite}=await import(process.env.PGLITE_MODULE || '@electric-sql/pglite');
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const db=new PGlite();
await db.exec(`create role anon;create role authenticated;create role service_role;
create table models(id uuid,status text,claimed_by text,heartbeat_at timestamptz);
create table social_commands(model_id uuid,id uuid,channel text,external_id text,account_scope text,operation text,text text,status text,lease_until timestamptz,worker_id text,context_ok boolean);
create function social_context_error(c social_commands) returns text language sql as $$select case when c.context_ok then null else 'stale_context' end$$;
create table persona(model_id uuid,cta_link text);
create table instagram(model_id uuid,connected boolean,enabled boolean,reply_mode text,ig_user_id text,circuit_until timestamptz,reply_comments boolean,reactions_enabled boolean,photos_enabled boolean,telegram_handle text,bio_link text,funnel_target text);
create table ig_users(model_id uuid,igsid text,human_takeover boolean,ai_enabled boolean,no_initiate boolean,no_links boolean,age_state text,last_source_mid text,last_incoming_at timestamptz,link_sent_at timestamptz,photo_sent_at timestamptz);
create table settings(model_id uuid,ai_paused boolean,paused_until timestamptz,flood_until timestamptz);
create table conversation_identities(model_id uuid,person_id uuid,platform text,external_id text,account_scope text);
create table conversation_people(model_id uuid,id uuid,no_initiate boolean,no_links boolean,age_state text,stopped_at timestamptz);
create table photos(model_id uuid,id uuid,url text,active boolean,spicy boolean,instagram_approved boolean);
create table instagram_actions(model_id uuid,id uuid,igsid text,kind text,state text,payload jsonb,lease_token uuid,lease_until timestamptz,expires_at timestamptz,source_at timestamptz,source_mid text,reserved_at timestamptz,contains_link boolean,contains_reminder boolean,reason text,text text,due_at timestamptz,attempts int default 0);
`);
const old=readFileSync('supabase/migrations/20261116152955_instagram_destination_budgets.sql','utf8');
for(const name of ['instagram_has_url','instagram_classify_link']){const i=old.indexOf('create function public.'+name+'(');await db.exec(old.slice(i,old.indexOf('$$;',i)+3));}
await db.exec(readFileSync('supabase/migrations/20261118005039_instagram_owner_fanvue_links.sql','utf8'));
await db.exec('create trigger store_target before insert or update of text,contains_link on instagram_actions for each row execute function instagram_store_link_target();');
const m='11111111-1111-4111-8111-111111111111',c='22222222-2222-4222-8222-222222222222',a='33333333-3333-4333-8333-333333333333',lease='44444444-4444-4444-8444-444444444444',url='https://www.fanvue.com/sima.sima';
async function reset(){await db.exec('truncate models,social_commands,persona,instagram,ig_users,instagram_actions;');
await db.query("insert into models values($1,'active','worker',now());",[m]);
await db.query('insert into persona values($1,$2)',[m,url]);
await db.query("insert into instagram values($1,true,true,'semi','account',null,false,false,false,'some_user','https://linkovne.com/model','both')",[m]);
await db.query("insert into ig_users values($1,'fan',false,true,false,false,'adult_self_declared','provider-mid',now()-interval '1 minute',now()-interval '10 days',null)",[m]);
await db.query("insert into social_commands values($1,$2,'instagram','fan','account','send_text',$3,'sending',now()+interval '2 minutes','worker',true)",[m,c,url]);
await db.query("insert into instagram_actions(model_id,id,igsid,kind,state,payload,lease_token,lease_until,expires_at,source_at,source_mid) values($1,$2,'fan','dm','leased',$3,$4,now()+interval '2 minutes',now()+interval '23 hours',now()-interval '1 minute','provider-mid')",[m,a,JSON.stringify({origin:'operator',command_id:c,account_id:'account',approved_source_mid:'provider-mid'}),lease]);}
const reserve=async(text=url)=> (await db.query('select instagram_reserve($1,$2,$3,$4,true,false) as r',[m,a,lease,text])).rows[0].r;
await reset();assert.equal((await reserve()).ok,true,'Explicit current owner Fanvue passes even with previous funnel link');
let sent=(await db.query('select * from instagram_actions')).rows[0];assert.equal(sent.state,'sending');assert.equal(sent.contains_link,true);assert.equal(sent.payload.link_target,'fanvue');
for(const operation of ['send_text','approve']){await reset();await db.query('update social_commands set operation=$1',[operation]);assert.equal((await reserve()).ok,true);}
await reset();await db.exec("update instagram set reply_mode='auto';update instagram_actions set payload=payload-'origin'-'command_id';update ig_users set link_sent_at=null;");assert.equal((await reserve()).ok,false,'Auto cannot send Fanvue');
await reset();await db.exec('delete from social_commands');assert.equal((await reserve()).reason,'operator_command_stale','Forged origin is insufficient');
for(const patch of ["context_ok=false","worker_id='foreign'","account_scope='old'","text='different'"]){await reset();await db.exec('update social_commands set '+patch);assert.equal((await reserve()).reason,'operator_command_stale');}
await reset();await db.exec("update ig_users set age_state='minor_or_conflicting'");assert.equal((await reserve()).ok,false,'Recipient guards remain');
await reset();await db.exec("update ig_users set no_links=true");assert.equal((await reserve()).ok,false);
await reset();await db.exec("update instagram_actions set expires_at=now()-interval '1 minute'");assert.equal((await reserve()).ok,false);
await reset();await db.exec("update persona set cta_link='https://fanvue.com/changed';update ig_users set link_sent_at=null;");assert.equal((await reserve()).ok,false,'Current destination is rechecked');
await reset();await db.query("insert into instagram_actions(model_id,id,igsid,kind,state,reserved_at,contains_link,payload,text) values($1,gen_random_uuid(),'another','dm','sent',now()-interval '1 minute',true,'{}',$2)",[m,url]);assert.equal((await reserve()).ok,false,'URL delivery budgets remain enforced');
assert.equal((await db.query("select instagram_configured_fanvue($1,'hello') as ok",[m])).rows[0].ok,false);
assert.equal((await db.query("select has_function_privilege('anon','instagram_configured_fanvue(uuid,text)','EXECUTE') as ok")).rows[0].ok,false);
console.log('PASS: exact configured owner Fanvue, manual/Semi, Auto/forged/stale rejected, recipient/window/quota guards, private grants');

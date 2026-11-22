import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {PGlite}=await import(process.env.PGLITE_MODULE);
const db=new PGlite();
await db.exec(`create role anon;create role authenticated;
create table settings(model_id uuid,tg_reply_mode text);
create table instagram(model_id uuid,reply_mode text,ig_user_id text);
create table fanvue(model_id uuid,reply_mode text);
create table pending_replies(id uuid primary key,model_id uuid,channel text,conv_key text,status text,source_message_id bigint,updated_at timestamptz);
create table social_contact_summaries(model_id uuid,channel text,external_id text,last_message_id text);
create table social_commands(model_id uuid,channel text,external_id text,operation text,status text);
create table instagram_actions(id uuid primary key,model_id uuid,igsid text,state text,kind text,text text,due_at timestamptz,reason text,lease_token uuid,lease_until timestamptz,payload jsonb,reserved_at timestamptz,provider_id text,expires_at timestamptz);
create table ig_users(model_id uuid,igsid text,ai_enabled boolean,human_takeover boolean);
create table dm_users(model_id uuid,tg_id bigint,ai_enabled boolean,human_takeover boolean,farewell_at timestamptz,last_incoming_at timestamptz,last_reply_at timestamptz,pending_reply boolean);
create table fv_users(model_id uuid,fan_uuid text,ai_enabled boolean,human_takeover boolean);
create table fv_messages(id bigint,model_id uuid,fan_uuid text,role text,content text,message_uuid text,occurred_at timestamptz);
create table fanvue_events(model_id uuid,event_id text,event_type text,payload jsonb,notified_at timestamptz,unique(model_id,event_id));`);
const m='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222';
const p='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',a='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
await db.query("insert into settings values($1,'semi')",[m]);
await db.query("insert into instagram values($1,'semi','account')",[m]);
await db.query("insert into fanvue values($1,'semi')",[m]);
await db.exec(readFileSync('supabase/migrations/20261122134945_social_auto_resume_pending.sql','utf8'));
const pending=async(channel,key,version='42')=>{
 await db.query('insert into pending_replies values($1,$2,$3,$4,\'awaiting\',$5,now())',[p,m,channel,key,version]);
 await db.query('insert into social_contact_summaries values($1,$2,$3,$4)',[m,channel,key.split(':')[0],version]);
};
const reset=async()=>{await db.exec('truncate pending_replies,social_contact_summaries,social_commands,instagram_actions,ig_users,dm_users,fv_users,fv_messages,fanvue_events');await db.query("update settings set tg_reply_mode='semi' where model_id=$1",[m]);await db.query("update instagram set reply_mode='semi' where model_id=$1",[m]);await db.query("update fanvue set reply_mode='semi' where model_id=$1",[m]);};
const status=async()=> (await db.query('select status from pending_replies where id=$1',[p])).rows[0].status;
for(const guard of ['none','takeover','busy','uncertain','expired','account','version','operator','reserved','delivered','skipped','foreign']){
 await reset();await pending('instagram','fan:'+a);
 await db.query('insert into ig_users values($1,\'fan\',true,$2)',[m,guard==='takeover']);
 await db.query("insert into instagram_actions(id,model_id,igsid,state,kind,text,payload,expires_at) values($1,$2,'fan','approval','dm','OLD SEMI TEXT',$3,now()+interval '1 hour')",[a,m,JSON.stringify({account_id:guard==='account'?'other':'account',approved_intent:'OLD SEMI TEXT',origin:guard==='operator'?'operator':'auto'})]);
 if(guard==='busy'||guard==='uncertain') await db.query("insert into social_commands values($1,'instagram','fan','approve',$2)",[m,guard==='busy'?'queued':'uncertain']);
 if(guard==='expired') await db.exec("update instagram_actions set expires_at=now()-interval '1 second'");
 if(guard==='version') await db.exec("update social_contact_summaries set last_message_id='43'");
 if(guard==='reserved') await db.exec("update instagram_actions set reserved_at=now()");
 if(guard==='delivered') await db.exec("update instagram_actions set provider_id='confirmed'");
 if(guard==='skipped') await db.exec("update pending_replies set status='skipped'");
 if(guard==='foreign') await db.query("update instagram_actions set model_id=$1",[other]);
 await db.query("update instagram set reply_mode='auto' where model_id=$1",[m]);
 assert.equal(await status(),guard==='none'?'superseded':guard==='skipped'?'skipped':'awaiting',guard);
 const row=(await db.query('select * from instagram_actions')).rows[0];
 assert.equal(row.state,guard==='none'?'pending':'approval',guard);
 if(guard==='none'){assert.equal(row.text,'');assert.equal(row.payload.approved_intent,undefined);}
}
await reset();await pending('telegram','123');await db.query("insert into dm_users values($1,123,true,false,null,now(),null,false)",[m]);await db.query("update settings set tg_reply_mode='auto' where model_id=$1",[m]);assert.equal(await status(),'superseded');assert.equal((await db.query('select pending_reply from dm_users')).rows[0].pending_reply,true);
await reset();await pending('fanvue','fan');await db.query("insert into fv_users values($1,'fan',true,false)",[m]);await db.query("insert into fv_messages values(42,$1,'fan','user','how are you','native-42',now()-interval '2 hours')",[m]);await db.query("update fanvue set reply_mode='auto' where model_id=$1",[m]);assert.equal(await status(),'superseded');let events=(await db.query('select * from fanvue_events')).rows;assert.equal(events.length,1);assert.equal(events[0].payload.data.text,'how are you');assert.equal(events[0].payload.data.uuid,'native-42');assert.equal(events[0].payload.data.sender,'fan');await db.query("update fanvue set reply_mode='auto' where model_id=$1",[m]);assert.equal((await db.query('select * from fanvue_events')).rows.length,1);

for(const guard of ['native','unknown','takeover','busy','stale']){
 await reset();await pending('fanvue','fan');
 await db.query("insert into fv_users values($1,'fan',true,$2)",[m,guard==='takeover']);
 await db.query("insert into fv_messages values(42,$1,'fan',$2,'already answered','m42',$3)",[m,guard==='native'?'assistant':'user',guard==='unknown'?null:new Date().toISOString()]);
 if(guard==='busy') await db.query("insert into social_commands values($1,'fanvue','fan','send_text','queued')",[m]);
 if(guard==='stale') await db.exec("update social_contact_summaries set last_message_id='43'");
 await db.query("update fanvue set reply_mode='auto' where model_id=$1",[m]);
 assert.equal((await db.query('select * from fanvue_events')).rows.length,0,guard);
 assert.equal(await status(),'awaiting',guard);
}
assert.equal((await db.query("select has_function_privilege('anon','social_resume_auto_pending()','EXECUTE') allowed")).rows[0].allowed,false);
console.log('PASS: Auto resumes pending TG/IG/FV, fresh regeneration, source/account/owner/takeover/window guards, no automatic repeat on same mode');
await db.close();

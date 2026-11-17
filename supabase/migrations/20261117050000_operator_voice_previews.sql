create table public.social_voice_previews (
 id uuid primary key,model_id uuid not null references models(id) on delete cascade,requested_by uuid not null references accounts(id),
 channel text not null check(channel in('telegram','fanvue')),external_id text not null,account_scope text not null,
 expected_source_id text,identity_id uuid,identity_updated_at timestamptz,pending_id uuid,expected_suggestions jsonb,
 cache_key text not null,
 text text not null check(length(text) between 1 and 1000),spoken text not null default '',ambience text not null default '',
 status text not null default 'queued' check(status in('queued','working','ready','failed')),error text not null default '',
 ogg_path text,mp3_path text,fanvue_media_uuid text,worker_id text,lease_token uuid,lease_until timestamptz,
 created_at timestamptz not null default now(),expires_at timestamptz not null default now()+interval '15 minutes',
 unique(model_id,id),check(ogg_path is null or ogg_path=model_id::text||'/voice-previews/'||id::text||'.ogg'),
 check(mp3_path is null or mp3_path=model_id::text||'/voice-previews/'||id::text||'.mp3')
);
alter table social_voice_previews enable row level security;
revoke all on social_voice_previews from public,anon,authenticated;grant all on social_voice_previews to service_role;
create index social_voice_previews_queue on social_voice_previews(model_id,status,created_at);
create function public.social_voice_current(v social_voice_previews) returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
declare c social_commands;
begin
 c.model_id:=v.model_id;c.channel:=v.channel;c.external_id:=v.external_id;c.account_scope:=v.account_scope;c.expected_source_id:=v.expected_source_id;c.identity_id:=v.identity_id;c.identity_updated_at:=v.identity_updated_at;
 return social_context_error(c) is null and (v.pending_id is null or exists(select 1 from pending_replies p where p.model_id=v.model_id and p.id=v.pending_id and p.status='awaiting' and p.suggestions=v.expected_suggestions));
end $$;
create function public.social_claim_voice(p_model uuid,p_worker text) returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare v social_voice_previews;
begin
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
 if not found then return null;end if;
 update social_voice_previews set status='failed',error='Voice preparation interrupted. Generate a new preview.' where model_id=p_model and ((status='working' and lease_until<now()) or (status='queued' and expires_at<now()));
 select * into v from social_voice_previews where model_id=p_model and status='queued' order by created_at,id for update skip locked limit 1;
 if not found then return null;end if;
 if not social_voice_current(v) then update social_voice_previews set status='failed',error='Conversation changed. Generate a fresh preview.' where id=v.id;return null;end if;
 update social_voice_previews set status='working',worker_id=p_worker,lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes' where id=v.id returning * into v;
 return to_jsonb(v);
end $$;
create function public.social_finish_voice(p_model uuid,p_worker text,p_id uuid,p_lease uuid,p_result jsonb) returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
declare v social_voice_previews;
begin
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
 if not found then return false;end if;
 select * into v from social_voice_previews where model_id=p_model and id=p_id and status='working' and lease_token=p_lease and lease_until>now() for update;
 if not found then return false;end if;
 if not social_voice_current(v) then p_result:=jsonb_build_object('error','Conversation changed. Generate a fresh preview.');end if;
 update social_voice_previews set status=case when coalesce(p_result->>'error','')<>'' then 'failed' else 'ready' end,
 error=coalesce(p_result->>'error',''),spoken=coalesce(p_result->>'spoken',''),ambience=coalesce(p_result->>'ambience',''),ogg_path=p_result->>'ogg_path',mp3_path=p_result->>'mp3_path',lease_until=null,expires_at=now()+interval '15 minutes' where id=v.id;
 return true;
end $$;
alter table social_commands add column voice_preview_id uuid;
alter table social_commands add foreign key(model_id,voice_preview_id) references social_voice_previews(model_id,id);
do $$ declare c record;begin
 for c in select conname from pg_constraint where conrelid='social_commands'::regclass and contype='c' and pg_get_constraintdef(oid) like '%operation%' loop
 execute format('alter table social_commands drop constraint %I',c.conname);end loop;
end $$;
alter table social_commands add check(operation in('approve','regenerate','send_text','send_media','send_voice')),
 add check(operation in('send_text','send_media','send_voice') or (pending_id is not null and expected_suggestions is not null)),
 add check(jsonb_typeof(media_uuids)='array' and ((operation='send_media' and channel='fanvue' and jsonb_array_length(media_uuids) between 1 and 20 and (price_cents=0 or price_cents>=300) and voice_preview_id is null)
 or (operation='send_voice' and channel in('telegram','fanvue') and media_uuids='[]' and voice_preview_id is not null and (price_cents=0 or (channel='fanvue' and price_cents>=300)))
 or (operation not in('send_media','send_voice') and media_uuids='[]' and price_cents=0 and voice_preview_id is null)));
create function public.social_enqueue_voice(p_model uuid,p_owner uuid,p_key uuid,p_preview uuid,p_price integer,p_channel text,p_external text,p_scope text,p_source text,p_text text) returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare v social_voice_previews;c social_commands;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 if not exists(select 1 from models where id=p_model and account_id=p_owner and model_type='persona') then raise exception 'owner required' using errcode='42501';end if;
 select * into c from social_commands where model_id=p_model and idempotency_key=p_key;
 if found then
  if c.requested_by is distinct from p_owner or c.operation<>'send_voice' or c.voice_preview_id is distinct from p_preview or c.price_cents is distinct from p_price or c.channel is distinct from p_channel or c.external_id is distinct from p_external or c.account_scope is distinct from p_scope or c.expected_source_id is distinct from p_source or c.text is distinct from p_text then raise exception 'idempotency key changed';end if;return to_jsonb(c);
 end if;
 select * into v from social_voice_previews where model_id=p_model and id=p_preview and requested_by=p_owner and status='ready' and expires_at>now() for share;
 if not found or v.channel is distinct from p_channel or v.external_id is distinct from p_external or v.account_scope is distinct from p_scope or v.expected_source_id is distinct from p_source or v.spoken is distinct from p_text or not social_voice_current(v) then raise exception 'Voice preview expired or conversation changed. Generate it again.';end if;
 if p_price is null or (p_price<>0 and (v.channel<>'fanvue' or p_price<300)) then raise exception 'invalid voice price';end if;
 insert into social_commands(model_id,requested_by,idempotency_key,operation,channel,external_id,account_scope,expected_source_id,identity_id,identity_updated_at,text,voice_preview_id,price_cents,pending_id,expected_suggestions)
 values(p_model,p_owner,p_key,'send_voice',v.channel,v.external_id,v.account_scope,v.expected_source_id,v.identity_id,v.identity_updated_at,v.spoken,v.id,p_price,v.pending_id,v.expected_suggestions) returning * into c;
 return to_jsonb(c);
end $$;
revoke all on function social_voice_current(social_voice_previews),social_claim_voice(uuid,text),social_finish_voice(uuid,text,uuid,uuid,jsonb),social_enqueue_voice(uuid,uuid,uuid,uuid,integer,text,text,text,text,text) from public,anon,authenticated;
grant execute on function social_voice_current(social_voice_previews),social_claim_voice(uuid,text),social_finish_voice(uuid,text,uuid,uuid,jsonb),social_enqueue_voice(uuid,uuid,uuid,uuid,integer,text,text,text,text,text) to service_role;

create index social_voice_preview_cache on social_voice_previews(model_id,cache_key,created_at desc);
create function public.social_request_voice(p_model uuid,p_owner uuid,p_id uuid,p_payload jsonb,p_regenerate boolean default false) returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare v social_voice_previews;c social_voice_previews;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text||':voice',0));
 if not exists(select 1 from models where id=p_model and account_id=p_owner and model_type='persona') then raise exception 'owner required' using errcode='42501';end if;
 c:=jsonb_populate_record(null::social_voice_previews,p_payload);c.id:=p_id;c.model_id:=p_model;c.requested_by:=p_owner;
 select * into v from social_voice_previews where model_id=p_model and id=p_id and requested_by=p_owner;
 if found then
  if row(v.channel,v.external_id,v.account_scope,v.expected_source_id,v.identity_id,v.identity_updated_at,v.pending_id,v.expected_suggestions,v.text,v.cache_key)
   is distinct from row(c.channel,c.external_id,c.account_scope,c.expected_source_id,c.identity_id,c.identity_updated_at,c.pending_id,c.expected_suggestions,c.text,c.cache_key) then raise exception 'voice request changed';end if;
  return to_jsonb(v);
 end if;
 if not social_voice_current(c) then raise exception 'Conversation changed. Generate a fresh voice preview.';end if;
 if not coalesce(p_regenerate,false) then
  select * into v from social_voice_previews where model_id=p_model and requested_by=p_owner and cache_key=c.cache_key and status in('queued','working','ready') and expires_at>now() order by created_at desc limit 1;
  if found then return to_jsonb(v);end if;
 end if;
 if (select count(*) from social_voice_previews where model_id=p_model and status in('queued','working') and expires_at>now())>=2 then raise exception 'Other voice previews are still preparing. Try again shortly.';end if;
 insert into social_voice_previews(id,model_id,requested_by,channel,external_id,account_scope,expected_source_id,identity_id,identity_updated_at,pending_id,expected_suggestions,text,cache_key)
 values(p_id,p_model,p_owner,c.channel,c.external_id,c.account_scope,c.expected_source_id,c.identity_id,c.identity_updated_at,c.pending_id,c.expected_suggestions,c.text,c.cache_key) returning * into v;
 return to_jsonb(v);
end $$;
revoke all on function social_request_voice(uuid,uuid,uuid,jsonb,boolean) from public,anon,authenticated;
grant execute on function social_request_voice(uuid,uuid,uuid,jsonb,boolean) to service_role;

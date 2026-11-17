-- Owner media intent uses the same durable/fenced delivery queue.
alter table public.social_commands add column media_uuids jsonb not null default '[]',add column price_cents integer not null default 0;
alter table public.social_commands drop constraint social_commands_operation_check,drop constraint social_commands_check1;
alter table public.social_commands add check(operation in('approve','regenerate','send_text','send_media')),
 add check(operation in('send_text','send_media') or (pending_id is not null and expected_suggestions is not null)),
 add check(jsonb_typeof(media_uuids)='array' and ((operation='send_media' and channel='fanvue' and jsonb_array_length(media_uuids) between 1 and 20 and (price_cents=0 or price_cents>=300)) or (operation<>'send_media' and media_uuids='[]' and price_cents=0)));
create or replace function public.social_preserve_intent() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
 if (to_jsonb(new)-array['status','worker_id','lease_token','lease_until','attempts','result','reason','updated_at','finished_at'])
  is distinct from (to_jsonb(old)-array['status','worker_id','lease_token','lease_until','attempts','result','reason','updated_at','finished_at']) then raise exception 'social command intent is immutable'; end if;
 return new;
end $$;

create function public.social_enqueue_fanvue_media(p_model uuid,p_owner uuid,p_key uuid,p_external text,p_scope text,p_source text,p_identity uuid,p_revision timestamptz,p_text text,p_media jsonb,p_price integer,p_pending uuid default null,p_suggestions jsonb default null)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare c social_commands; prior social_commands; pending pending_replies; err text;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 if not exists(select 1 from models where id=p_model and account_id=p_owner and model_type='persona') then raise exception 'model owner required' using errcode='42501'; end if;
 c.model_id:=p_model;c.requested_by:=p_owner;c.idempotency_key:=p_key;c.operation:='send_media';c.channel:='fanvue';c.external_id:=p_external;c.account_scope:=p_scope;
 c.expected_source_id:=p_source;c.identity_id:=p_identity;c.identity_updated_at:=p_revision;c.text:=coalesce(p_text,'');c.media_uuids:=p_media;c.price_cents:=p_price;c.pending_id:=p_pending;c.expected_suggestions:=p_suggestions;
 select * into prior from social_commands where model_id=p_model and idempotency_key=p_key;
 if found then
  if row(prior.operation,prior.channel,prior.external_id,prior.account_scope,prior.expected_source_id,prior.identity_id,prior.identity_updated_at,prior.text,prior.media_uuids,prior.price_cents,prior.pending_id,prior.expected_suggestions)
   is distinct from row(c.operation,c.channel,c.external_id,c.account_scope,c.expected_source_id,c.identity_id,c.identity_updated_at,c.text,c.media_uuids,c.price_cents,c.pending_id,c.expected_suggestions) then raise exception 'idempotency key reused'; end if;
  return to_jsonb(prior);
 end if;
 if p_key is null or p_media is null or jsonb_typeof(p_media)<>'array' or jsonb_array_length(p_media) not between 1 and 20 or p_price is null or (p_price<>0 and p_price<300) or length(c.text)>4000 then raise exception 'invalid media intent'; end if;
 if exists(select 1 from jsonb_array_elements_text(p_media) x where x !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') or (select count(distinct x) from jsonb_array_elements_text(p_media)x)<>jsonb_array_length(p_media) then raise exception 'invalid media IDs'; end if;
 err:=social_context_error(c);if err is not null then raise exception '%',err;end if;
 if p_pending is not null then
  select * into pending from pending_replies where model_id=p_model and id=p_pending for update;
  if not found or pending.status<>'awaiting' or pending.channel<>'fanvue' or pending.conv_key<>p_external or pending.suggestions is distinct from p_suggestions then raise exception 'proposal changed'; end if;
 end if;
 insert into social_commands(model_id,requested_by,idempotency_key,operation,channel,external_id,account_scope,expected_source_id,identity_id,identity_updated_at,text,media_uuids,price_cents,pending_id,expected_suggestions)
 values(p_model,p_owner,p_key,'send_media','fanvue',p_external,p_scope,p_source,p_identity,p_revision,c.text,p_media,p_price,p_pending,p_suggestions) returning * into c;
 return to_jsonb(c);
end $$;
revoke all on function public.social_enqueue_fanvue_media(uuid,uuid,uuid,text,text,text,uuid,timestamptz,text,jsonb,integer,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.social_enqueue_fanvue_media(uuid,uuid,uuid,text,text,text,uuid,timestamptz,text,jsonb,integer,uuid,jsonb) to service_role;

-- Read/upload control only: never sends a chat message. Bytes go browser → Fanvue S3.
create table public.social_fanvue_requests(
 id uuid primary key,model_id uuid not null references models(id) on delete cascade,account_scope text not null,
 action text not null check(action in('list','init','part','complete','status')),input jsonb not null,
 status text not null default 'queued' check(status in('queued','working','done','failed')),output jsonb not null default '{}',error text not null default '',
 worker_id text,lease_token uuid,lease_until timestamptz,created_at timestamptz not null default now(),expires_at timestamptz not null default now()+interval '24 hours'
);
create index social_fanvue_requests_queue on public.social_fanvue_requests(model_id,status,created_at);
alter table public.social_fanvue_requests enable row level security;
revoke all on public.social_fanvue_requests from public,anon,authenticated;grant all on public.social_fanvue_requests to service_role;
create function public.social_claim_fanvue_request(p_model uuid,p_worker text) returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare r social_fanvue_requests;
begin
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;if not found then return null;end if;
 update social_fanvue_requests set status='failed',error='Upload request interrupted. Retry from the media picker.' where model_id=p_model and ((status='working' and lease_until<now()) or (status='queued' and expires_at<=now()));
 select * into r from social_fanvue_requests where model_id=p_model and status='queued' and expires_at>now() order by created_at,id for update skip locked limit 1;
 if not found then return null;end if;
 update social_fanvue_requests set status='working',worker_id=p_worker,lease_token=gen_random_uuid(),lease_until=now()+interval '2 minutes' where id=r.id returning * into r;
 return to_jsonb(r);
end $$;
create function public.social_finish_fanvue_request(p_model uuid,p_worker text,p_id uuid,p_lease uuid,p_output jsonb,p_error text default '') returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
begin
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;if not found then return false;end if;
 update social_fanvue_requests set status=case when p_error='' then 'done' else 'failed' end,output=p_output,error=p_error,lease_until=null where model_id=p_model and id=p_id and worker_id=p_worker and lease_token=p_lease and status='working' and lease_until>now();
 return found;
end $$;
revoke all on function public.social_claim_fanvue_request(uuid,text),public.social_finish_fanvue_request(uuid,text,uuid,uuid,jsonb,text) from public,anon,authenticated;
grant execute on function public.social_claim_fanvue_request(uuid,text),public.social_finish_fanvue_request(uuid,text,uuid,uuid,jsonb,text) to service_role;

-- Runtime scheduling is mutable; the approved intent is not.
alter table public.social_commands add column available_at timestamptz not null default now();
create or replace function public.social_preserve_intent() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
 if (to_jsonb(new)-array['status','worker_id','lease_token','lease_until','attempts','result','reason','updated_at','finished_at','available_at'])
  is distinct from (to_jsonb(old)-array['status','worker_id','lease_token','lease_until','attempts','result','reason','updated_at','finished_at','available_at']) then raise exception 'social command intent is immutable'; end if;
 return new;
end $$;
create or replace function public.social_claim(p_model uuid,p_worker text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare c social_commands;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
  if not found then return null; end if;
  update social_commands set status='uncertain',reason='send_lease_expired',updated_at=now(),finished_at=now()
    where model_id=p_model and status='sending' and lease_until<=now();
  update social_commands set status='queued',worker_id=null,lease_token=null,lease_until=null,updated_at=now()
    where model_id=p_model and status='working' and lease_until<=now();
  select * into c from social_commands sc where sc.model_id=p_model and sc.status='queued' and sc.available_at<=now()
    and (sc.channel<>'instagram' or sc.operation='regenerate' or not exists(
      select 1 from instagram_actions recent where recent.model_id=sc.model_id
        and recent.reserved_at>now()-interval '45 seconds'))
    and not exists(select 1 from social_commands earlier where earlier.model_id=sc.model_id and earlier.channel=sc.channel
      and earlier.account_scope=sc.account_scope and earlier.external_id=sc.external_id and earlier.status='queued'
      and (earlier.created_at,earlier.id)<(sc.created_at,sc.id))
    and not exists(select 1 from social_commands busy where busy.model_id=sc.model_id and busy.channel=sc.channel and busy.account_scope=sc.account_scope and busy.external_id=sc.external_id and busy.status in ('working','sending'))
    order by sc.created_at,sc.id for update skip locked limit 1;
  if not found then return null; end if;
  update social_commands set status='working',worker_id=p_worker,lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes',attempts=attempts+1,updated_at=now()
    where id=c.id returning * into c;
  return to_jsonb(c);
end $$;
-- Only a known local reservation denial BEFORE any provider write may wait.
create function public.social_defer(p_model uuid,p_worker text,p_command uuid,p_lease uuid,p_action uuid,p_reason text)
returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
declare c social_commands;a instagram_actions;next_at timestamptz;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
 if not found then return false;end if;
 if p_reason is null or p_reason not in('action_gap','account_limit','dm_limit','conversation_limit','active_chats_limit','new_contact_limit','url_limit','url_global_limit','reminder_limit') then return false;end if;
 select * into c from social_commands where model_id=p_model and id=p_command and status='sending' and worker_id=p_worker and lease_token=p_lease and lease_until>now() and channel='instagram' and operation in('approve','send_text') for update;
 if not found or social_context_error(c) is not null then return false;end if;
 select * into a from instagram_actions where model_id=p_model and id=p_action for update;
 if not found or a.state not in('pending','blocked') or a.reason is distinct from p_reason or a.reserved_at is not null or coalesce(a.provider_id,'')<>''
  or a.igsid<>c.external_id or a.payload->>'command_id' is distinct from c.id::text or a.payload->>'origin' is distinct from 'operator' or a.payload->>'account_id' is distinct from c.account_scope then return false;end if;
 if c.pending_id is not null then
  perform 1 from pending_replies where model_id=p_model and id=c.pending_id and status='sent' and decision_command_id=c.id and chosen_text is null and suggestions=c.expected_suggestions for update;
  if not found then return false;end if;
 end if;
 if p_reason='action_gap' then
  select greatest(now()+interval '2 seconds',coalesce(max(reserved_at)+interval '46 seconds',now())) into next_at from instagram_actions where model_id=p_model;
 else next_at:=now()+case when p_reason in('new_contact_limit','url_limit','url_global_limit','reminder_limit') then interval '15 minutes' else interval '1 minute' end;
 end if;
 update instagram_actions set state='approval',lease_token=null,lease_until=null where model_id=p_model and id=a.id;
 update pending_replies set status='awaiting',decision_command_id=null,decided_at=null,updated_at=now() where model_id=p_model and id=c.pending_id and decision_command_id=c.id;
 update social_commands set status='queued',available_at=next_at,worker_id=null,lease_token=null,lease_until=null,finished_at=null,reason='waiting_'||p_reason,
  result=jsonb_build_object('deferred_action_id',a.id),updated_at=now() where model_id=p_model and id=c.id;
 return true;
end $$;
revoke all on function social_defer(uuid,text,uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function social_defer(uuid,text,uuid,uuid,uuid,text) to service_role;

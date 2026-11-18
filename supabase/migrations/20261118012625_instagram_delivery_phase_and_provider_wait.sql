-- Persist the actual message API boundary, separately from reservation/read receipts.
create function public.instagram_start_message(p_model uuid,p_action uuid,p_lease uuid)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 select * into a from instagram_actions where model_id=p_model and id=p_action and state='sending' and lease_token=p_lease and lease_until>now() for update;
 if not found or a.payload ? 'message_api_started_at' or coalesce(a.provider_id,'')<>'' then return false;end if;
 if a.payload->>'origin'='operator' and not exists(select 1 from social_commands c join models m on m.id=c.model_id
   where c.model_id=p_model and c.id::text=a.payload->>'command_id' and c.status='sending' and c.text=a.text
     and c.external_id=a.igsid and c.account_scope=a.payload->>'account_id' and c.lease_until>now()
     and c.worker_id=m.claimed_by and m.status='active' and m.heartbeat_at>now()-interval '90 seconds' and social_context_error(c) is null) then return false;end if;
 update instagram_actions set payload=payload||jsonb_build_object('message_api_started_at',now()) where model_id=p_model and id=a.id;
 return true;
end $$;
revoke all on function instagram_start_message(uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function instagram_start_message(uuid,uuid,uuid) to service_role;

create or replace function public.instagram_release_unsent(p_model uuid,p_action uuid,p_lease uuid,p_reason text)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 update instagram_actions set state='pending',reserved_at=null,lease_token=null,lease_until=null,due_at=now()+interval '1 minute',reason=p_reason
 where model_id=p_model and id=p_action and lease_token=p_lease and state='sending'
   and not(payload ? 'message_api_started_at') and coalesce(provider_id,'')='';
 return found;
end $$;
revoke all on function instagram_release_unsent(uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function instagram_release_unsent(uuid,uuid,uuid,text) to service_role;

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
    and (sc.channel<>'instagram' or sc.operation='regenerate' or not exists(select 1 from instagram paused where paused.model_id=sc.model_id and paused.circuit_until>now()))
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

create or replace function public.social_defer(p_model uuid,p_worker text,p_command uuid,p_lease uuid,p_action uuid,p_reason text)
returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
declare c social_commands;a instagram_actions;next_at timestamptz;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
 if not found then return false;end if;
 if p_reason is null or p_reason not in('action_gap','account_limit','dm_limit','conversation_limit','active_chats_limit','new_contact_limit','url_limit','url_global_limit','reminder_limit','provider_read_limit','provider_read_unavailable','meta_4','provider_pause') then return false;end if;
 select * into c from social_commands where model_id=p_model and id=p_command and status='sending' and worker_id=p_worker and lease_token=p_lease and lease_until>now() and channel='instagram' and operation in('approve','send_text') for update;
 if not found or social_context_error(c) is not null then return false;end if;
 select * into a from instagram_actions where model_id=p_model and id=p_action for update;
 if not found or a.state not in('pending','blocked') or a.reason is distinct from p_reason or a.reserved_at is not null or coalesce(a.provider_id,'')<>''
  or a.igsid<>c.external_id or a.payload->>'command_id' is distinct from c.id::text or a.payload->>'origin' is distinct from 'operator' or a.payload->>'account_id' is distinct from c.account_scope then return false;end if;
 if p_reason in('provider_read_limit','provider_read_unavailable','provider_pause') and a.payload ? 'message_api_started_at' then return false;end if;
 if p_reason='meta_4' and (a.state<>'blocked' or a.payload->>'last_rejected_reason' is distinct from 'meta_4' or a.payload->>'last_rejected_message_api_at' is null or a.payload ? 'message_api_started_at') then return false;end if;
 if c.pending_id is not null then
  perform 1 from pending_replies where model_id=p_model and id=c.pending_id and status='sent' and decision_command_id=c.id and chosen_text is null and suggestions=c.expected_suggestions for update;
  if not found then return false;end if;
 end if;
 if p_reason in('provider_read_limit','provider_read_unavailable','meta_4','provider_pause') then
  select greatest(now()+interval '1 minute',coalesce(circuit_until,now())) into next_at from instagram where model_id=p_model;
  next_at:=coalesce(next_at,now()+interval '1 minute');
 elsif p_reason='action_gap' then
  select greatest(now()+interval '2 seconds',coalesce(max(reserved_at)+interval '46 seconds',now())) into next_at from instagram_actions where model_id=p_model;
 else next_at:=now()+case when p_reason in('new_contact_limit','url_limit','url_global_limit','reminder_limit') then interval '15 minutes' else interval '1 minute' end;
 end if;
 update instagram_actions set state='approval',lease_token=null,lease_until=null where model_id=p_model and id=a.id;
 update pending_replies set status='awaiting',decision_command_id=null,decided_at=null,updated_at=now() where model_id=p_model and id=c.pending_id and decision_command_id=c.id;
 update social_commands set status='queued',available_at=next_at,worker_id=null,lease_token=null,lease_until=null,finished_at=null,reason='waiting_'||p_reason,
  result=jsonb_build_object('deferred_action_id',a.id),updated_at=now() where model_id=p_model and id=c.id;
 return true;
end $$;

create or replace function public.instagram_finish(p_model uuid,p_action uuid,p_lease uuid,p_outcome text,p_provider text default '',p_reason text default '')
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into a from instagram_actions where model_id=p_model and id=p_action for update;
  if not found or a.lease_token is distinct from p_lease or a.state not in ('sending','uncertain') then return false; end if;
  if p_outcome not in ('sent','uncertain','failed') then raise exception 'invalid outcome'; end if;
  update instagram_actions set state=case when p_outcome='failed' then 'blocked' else p_outcome end,
    reserved_at=case when p_outcome='failed' then null else reserved_at end,
    payload=case when p_outcome='failed' then (payload-'message_api_started_at')||jsonb_build_object('last_rejected_message_api_at',payload->'message_api_started_at','last_rejected_reason',p_reason) else payload end,
    sent_at=case when p_outcome='sent' then now() else null end,provider_id=nullif(p_provider,''),reason=p_reason,lease_until=null
    where model_id=p_model and id=a.id;
  if p_outcome='sent' and a.kind<>'comment' then
    update ig_users set last_reply_at=now(),msg_count=msg_count+case when a.kind='reaction' then 0 else 1 end,
      photo_sent_at=case when a.kind='photo' then now() else photo_sent_at end,
      link_sent_at=case when a.contains_link then now() else link_sent_at end,
      last_reminder_at=case when a.contains_reminder then now() else last_reminder_at end
      where model_id=p_model and igsid=a.igsid;
  end if;
  return true;
end $$;

-- Read-only preparation can wait before any provider-message boundary is entered.
create function public.social_defer_preparation(p_model uuid,p_worker text,p_command uuid,p_lease uuid,p_reason text)
returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
declare c social_commands;next_at timestamptz;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
 if not found or p_reason is null or p_reason not in('provider_read_limit','provider_read_unavailable') then return false;end if;
 select * into c from social_commands where model_id=p_model and id=p_command and status='working' and worker_id=p_worker and lease_token=p_lease and lease_until>now() and channel='instagram' and operation in('approve','send_text') for update;
 if not found or social_context_error(c) is not null then return false;end if;
 if exists(select 1 from instagram_actions where model_id=p_model and payload->>'command_id'=c.id::text
   and (state in('sending','uncertain','sent') or reserved_at is not null or coalesce(provider_id,'')<>'' or payload ? 'message_api_started_at')) then return false;end if;
 select greatest(now()+interval '1 minute',coalesce(circuit_until,now())) into next_at from instagram where model_id=p_model;
 update social_commands set status='queued',available_at=coalesce(next_at,now()+interval '1 minute'),worker_id=null,lease_token=null,lease_until=null,finished_at=null,reason='waiting_'||p_reason,updated_at=now() where model_id=p_model and id=c.id;
 return true;
end $$;
revoke all on function social_defer_preparation(uuid,text,uuid,uuid,text) from public,anon,authenticated;
grant execute on function social_defer_preparation(uuid,text,uuid,uuid,text) to service_role;

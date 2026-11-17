-- UI dismissal is presentation only: neither message history nor delivery state changes.
alter table social_commands add column ui_dismissed_at timestamptz;
create or replace function social_preserve_intent() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
 if (to_jsonb(new)-array['status','worker_id','lease_token','lease_until','attempts','result','reason','updated_at','finished_at','available_at','ui_dismissed_at'])
 is distinct from (to_jsonb(old)-array['status','worker_id','lease_token','lease_until','attempts','result','reason','updated_at','finished_at','available_at','ui_dismissed_at']) then raise exception 'social command intent is immutable';end if;
 return new;
end $$;
do $$ declare c record;begin
 for c in select conname from pg_constraint where conrelid='social_commands'::regclass and contype='c' and pg_get_constraintdef(oid) like '%operation%' and pg_get_constraintdef(oid) like '%pending_id%' loop
 execute format('alter table social_commands drop constraint %I',c.conname);end loop;
end $$;
alter table social_commands add constraint social_commands_proposal_required check(operation in('regenerate','send_text','send_media','send_voice') or (pending_id is not null and expected_suggestions is not null));
create or replace function public.social_enqueue(p_model uuid,p_requested_by uuid,p_key uuid,p_operation text,p_channel text,p_external text,p_scope text,p_pending uuid,p_suggestions jsonb,p_source text,p_identity uuid,p_identity_updated_at timestamptz,p_text text,p_brief text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare c social_commands; existing social_commands; p pending_replies; error text;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  if not exists(select 1 from models where id=p_model and account_id=p_requested_by and model_type='persona') then raise exception 'model owner required' using errcode='42501'; end if;
  c.model_id:=p_model; c.requested_by:=p_requested_by; c.idempotency_key:=p_key; c.operation:=p_operation;
  c.channel:=p_channel; c.external_id:=p_external; c.account_scope:=p_scope; c.pending_id:=p_pending;
  c.expected_suggestions:=p_suggestions; c.expected_source_id:=p_source; c.identity_id:=p_identity; c.identity_updated_at:=p_identity_updated_at;
  c.text:=coalesce(p_text,''); c.brief:=coalesce(p_brief,'');
  select * into existing from social_commands where model_id=p_model and idempotency_key=p_key;
  if found then
    if row(existing.requested_by,existing.operation,existing.channel,existing.external_id,existing.account_scope,existing.pending_id,existing.expected_suggestions,existing.expected_source_id,existing.identity_id,existing.identity_updated_at,existing.text,existing.brief)
      is distinct from row(c.requested_by,c.operation,c.channel,c.external_id,c.account_scope,c.pending_id,c.expected_suggestions,c.expected_source_id,c.identity_id,c.identity_updated_at,c.text,c.brief) then raise exception 'idempotency key reused for different intent'; end if;
    return to_jsonb(existing);
  end if;
  if p_key is null or p_operation is null or p_operation not in ('approve','regenerate','send_text') or p_channel is null or p_channel not in ('telegram','fanvue','instagram') then raise exception 'invalid operation'; end if;
  if length(c.text)>10000 or length(c.brief)>2000 or (p_operation in ('approve','send_text') and btrim(c.text)='') then raise exception 'invalid text'; end if;
  if p_channel='instagram' and p_operation in ('approve','send_text') and octet_length(c.text)>1000 then raise exception 'instagram text too long'; end if;
  if p_operation='approve' and (p_pending is null or p_suggestions is null or jsonb_typeof(p_suggestions)<>'array') then raise exception 'proposal snapshot required'; end if;
  error:=social_context_error(c); if error is not null then raise exception '%',error; end if;
  if p_pending is not null then
    select * into p from pending_replies where model_id=p_model and id=p_pending for update;
    if not found or p.status<>'awaiting' or p.channel<>p_channel or not(p.conv_key=p_external or (p_channel='instagram' and split_part(p.conv_key,':',1)=p_external)) or p.suggestions is distinct from p_suggestions then raise exception 'stale or foreign proposal'; end if;
    if p_operation='approve' and not(p.suggestions @> jsonb_build_array(c.text))
    and not(p_channel='instagram' and exists(select 1 from instagram cfg cross join lateral jsonb_array_elements_text(p.suggestions) v
      where cfg.model_id=p_model and social_render_instagram_text(v.value,cfg)=c.text)) then raise exception 'approved text is not a suggestion'; end if;
  end if;
  insert into social_commands(model_id,requested_by,idempotency_key,operation,channel,external_id,account_scope,pending_id,expected_suggestions,expected_source_id,identity_id,identity_updated_at,text,brief)
    values(p_model,p_requested_by,p_key,p_operation,p_channel,p_external,p_scope,p_pending,p_suggestions,p_source,p_identity,p_identity_updated_at,c.text,c.brief) returning * into c;
  return to_jsonb(c);
end $$;
create function social_store_owner_draft(p_model uuid,p_worker text,p_command uuid,p_lease uuid,p_suggestions jsonb) returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
declare c social_commands;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
 perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
 if not found then return false;end if;
 select * into c from social_commands where model_id=p_model and id=p_command and operation='regenerate' and pending_id is null and status='working' and worker_id=p_worker and lease_token=p_lease and lease_until>now() for update;
 if not found or social_context_error(c) is not null then return false;end if;
 if jsonb_typeof(p_suggestions) is distinct from 'array' or jsonb_array_length(p_suggestions) not between 1 and 3 then return false;end if;
 if exists(select 1 from jsonb_array_elements(p_suggestions) v where jsonb_typeof(v)<>'string' or length(v#>>'{}') not between 1 and 4000) then return false;end if;
 update social_commands set status='done',result=jsonb_build_object('owner_suggestions',p_suggestions),reason='',finished_at=now(),updated_at=now() where model_id=p_model and id=c.id;
 return true;
end $$;
create function social_dismiss_command(p_model uuid,p_owner uuid,p_command uuid,p_channel text,p_external text,p_scope text) returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
declare c social_commands;
begin
 if not exists(select 1 from models where id=p_model and account_id=p_owner and model_type='persona') then return false;end if;
 select * into c from social_commands where model_id=p_model and id=p_command and channel=p_channel and external_id=p_external and account_scope=p_scope for update;
 if not found or not (c.status in('failed','blocked','stale') or (c.operation='regenerate' and c.status='done' and jsonb_typeof(c.result->'owner_suggestions')='array')) or coalesce(c.result->>'delivery_state','') in('sending','uncertain','sent','delivered') or coalesce(c.result->>'provider_message_id','')<>'' then return false;end if;
 if c.channel='instagram' and exists(select 1 from instagram_actions where model_id=p_model and id::text=c.result->>'action_id' and state in('sending','uncertain','sent')) then return false;end if;
 update social_commands set ui_dismissed_at=coalesce(ui_dismissed_at,now()) where model_id=p_model and id=c.id;
 return true;
end $$;
revoke all on function social_store_owner_draft(uuid,text,uuid,uuid,jsonb),social_dismiss_command(uuid,uuid,uuid,text,text,text) from public,anon,authenticated;
grant execute on function social_store_owner_draft(uuid,text,uuid,uuid,jsonb),social_dismiss_command(uuid,uuid,uuid,text,text,text) to service_role;

-- One durable operator queue; provider sends stay in the leased tenant worker.
create table public.social_commands (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references public.models(id) on delete cascade,
  requested_by uuid not null references public.accounts(id),
  idempotency_key uuid not null,
  operation text not null check(operation in ('approve','regenerate','send_text')),
  channel text not null check(channel in ('telegram','fanvue','instagram')),
  external_id text not null check(btrim(external_id)<>''),
  account_scope text not null check(btrim(account_scope)<>''),
  pending_id uuid,
  expected_suggestions jsonb,
  expected_source_id text,
  identity_id uuid,
  identity_updated_at timestamptz,
  text text not null default '', brief text not null default '',
  status text not null default 'queued' check(status in ('queued','working','sending','done','blocked','stale','failed','uncertain')),
  worker_id text, lease_token uuid, lease_until timestamptz,
  attempts integer not null default 0,
  result jsonb not null default '{}', reason text not null default '',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), finished_at timestamptz,
  unique(model_id,idempotency_key), unique(model_id,id),
  foreign key(model_id,identity_id) references public.conversation_identities(model_id,id),
  check((identity_id is null)=(identity_updated_at is null)),
  check(expected_suggestions is null or jsonb_typeof(expected_suggestions)='array'),
  check(operation='send_text' or (pending_id is not null and expected_suggestions is not null))
);
create unique index social_commands_contact_work on public.social_commands(model_id,channel,account_scope,external_id)
  where status in ('working','sending');
create unique index instagram_actions_operator_command on public.instagram_actions(model_id,(payload->>'command_id'))
  where payload->>'origin'='operator' and payload->>'command_id' is not null;
create index social_commands_queue on public.social_commands(model_id,created_at,id) where status='queued';
create unique index pending_replies_model_id_id on public.pending_replies(model_id,id);
alter table public.social_commands add foreign key(model_id,pending_id) references public.pending_replies(model_id,id);
alter table public.pending_replies add column decision_command_id uuid;
alter table public.pending_replies add foreign key(model_id,decision_command_id) references public.social_commands(model_id,id);
alter table public.social_commands enable row level security;
revoke all on public.social_commands from public,anon,authenticated;
grant select,insert,update,delete on public.social_commands to service_role;

-- Provider intent cannot drift between idempotent HTTP retries and worker delivery.
create function public.social_preserve_intent() returns trigger
language plpgsql set search_path=public,pg_temp as $$
begin
  if row(new.id,new.model_id,new.requested_by,new.idempotency_key,new.operation,new.channel,new.external_id,new.account_scope,new.pending_id,new.expected_suggestions,new.expected_source_id,new.identity_id,new.identity_updated_at,new.text,new.brief)
    is distinct from row(old.id,old.model_id,old.requested_by,old.idempotency_key,old.operation,old.channel,old.external_id,old.account_scope,old.pending_id,old.expected_suggestions,old.expected_source_id,old.identity_id,old.identity_updated_at,old.text,old.brief) then
    raise exception 'social command intent is immutable';
  end if;
  return new;
end $$;
create trigger social_preserve_intent before update on public.social_commands for each row execute function public.social_preserve_intent();
revoke all on function public.social_preserve_intent() from public,anon,authenticated;

-- An unchanged observation is not a new identity version.
create or replace function public.conversation_ensure_identity(p_model uuid,p_platform text,p_external text,p_scope text default 'primary',p_username text default '',p_name text default '')
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare i conversation_identities; p uuid; username_new text; name_new text;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into i from conversation_identities where model_id=p_model and platform=p_platform and external_id=p_external and account_scope=p_scope;
  if not found then
    insert into conversation_people(model_id) values(p_model) returning id into p;
    insert into conversation_identities(model_id,person_id,platform,external_id,account_scope,username,display_name)
      values(p_model,p,p_platform,p_external,p_scope,coalesce(p_username,''),coalesce(p_name,'')) returning * into i;
  else
    username_new:=coalesce(nullif(p_username,''),i.username); name_new:=coalesce(nullif(p_name,''),i.display_name);
    if username_new is distinct from i.username or name_new is distinct from i.display_name then
      update conversation_identities set username=username_new,display_name=name_new,updated_at=clock_timestamp()
        where model_id=p_model and id=i.id returning * into i;
    end if;
  end if;
  return to_jsonb(i);
end $$;

create view public.social_contact_summaries with(security_invoker=true) as
with contacts as (
  select u.model_id,'telegram'::text channel,u.tg_id::text external_id,
    case when coalesce(cfg.tg_session_enc,'')<>'' then 'telegram:'||md5(cfg.tg_session_enc) else 'primary' end account_scope,
    coalesce(nullif(u.first_name,''),nullif(u.username,''),u.tg_id::text) display_name,coalesce(u.username,'') username,
    ''::text avatar_url,u.ai_enabled,u.human_takeover,u.summary,0::integer spent_cents,u.last_incoming_at,u.last_reply_at,u.created_at
  from public.dm_users u join public.models cfg on cfg.id=u.model_id
  union all
  select u.model_id,'fanvue',u.fan_uuid,case when coalesce(cfg.creator_uuid,'')<>'' then 'fanvue:'||cfg.creator_uuid else 'primary' end,coalesce(nullif(u.display_name,''),nullif(u.handle,''),u.fan_uuid),
    u.handle,u.avatar_url,u.ai_enabled,u.human_takeover,u.summary,u.spent_cents,u.last_incoming_at,u.last_reply_at,u.first_seen
  from public.fv_users u left join public.fanvue cfg on cfg.model_id=u.model_id
  union all
  select u.model_id,'instagram',u.igsid,cfg.ig_user_id,coalesce(nullif(u.name,''),nullif(u.username,''),u.igsid),
    u.username,'',u.ai_enabled,u.human_takeover,u.summary,0,u.last_incoming_at,u.last_reply_at,u.created_at
  from public.ig_users u join public.instagram cfg on cfg.model_id=u.model_id where cfg.ig_user_id<>''
    and (exists(select 1 from public.conversation_identities current_i where current_i.model_id=u.model_id and current_i.platform='instagram' and current_i.external_id=u.igsid and current_i.account_scope=cfg.ig_user_id)
      or not exists(select 1 from public.conversation_identities old_i where old_i.model_id=u.model_id and old_i.platform='instagram' and old_i.external_id=u.igsid))
), messages as (
  select model_id,'telegram'::text channel,tg_id::text external_id,id,role,content,created_at source_at,created_at ingestion_at from public.dm_messages
  union all
  select model_id,'fanvue',fan_uuid,id,role,content,occurred_at,created_at from public.fv_messages
  union all
  select model_id,'instagram',igsid,id,role,content,occurred_at,created_at from public.ig_messages
)
select c.model_id,c.channel,c.external_id,c.account_scope,i.id identity_id,i.person_id,i.status identity_status,i.candidate_id,
  i.updated_at identity_updated_at,c.display_name,c.username,c.avatar_url,c.ai_enabled,c.human_takeover,c.summary,c.spent_cents,
  c.last_incoming_at,c.last_reply_at,m.context_id::text last_message_id,m.role last_message_role,m.content last_message_text,
  m.source_at last_message_at,coalesce(greatest(m.source_at,c.last_incoming_at,c.last_reply_at),c.created_at) last_activity_at,
  p.id pending_id,coalesce(m.role='user',false) needs_reply
from contacts c
left join public.conversation_identities i on i.model_id=c.model_id and i.platform=c.channel and i.external_id=c.external_id and i.account_scope=case when c.channel='instagram' then c.account_scope else 'primary' end
-- The timeline follows provider time. Its version follows every stored message,
-- including a late import whose original timestamp is older or unavailable.
left join lateral (select msg.*,max(msg.id) over() context_id from messages msg where msg.model_id=c.model_id and msg.channel=c.channel and msg.external_id=c.external_id
  order by msg.source_at desc nulls last,msg.id desc limit 1) m on true
left join lateral (select pr.id from public.pending_replies pr where pr.model_id=c.model_id and pr.channel=c.channel and pr.status='awaiting'
  and (pr.conv_key=c.external_id or (c.channel='instagram' and split_part(pr.conv_key,':',1)=c.external_id))
  order by pr.created_at desc,pr.id desc limit 1) p on true;
revoke all on public.social_contact_summaries from public,anon,authenticated;
grant select on public.social_contact_summaries to service_role;

create function public.social_inbox(p_model uuid,p_search text,p_channel text,p_filter text,p_limit int,p_offset int,p_allow_instagram boolean)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare output jsonb;
begin
  if coalesce(p_channel,'') not in ('','telegram','fanvue','instagram') or coalesce(p_filter,'all') not in ('all','needs_reply','approvals','manual') then raise exception 'invalid filter'; end if;
  with allowed as (
    select s.*,(s.human_takeover or not s.ai_enabled
      or (s.channel='telegram' and exists(select 1 from settings cfg where cfg.model_id=s.model_id and cfg.tg_reply_mode='off'))
      or (s.channel='fanvue' and exists(select 1 from fanvue cfg where cfg.model_id=s.model_id and (not cfg.enabled or cfg.reply_mode='off')))
      or (s.channel='instagram' and exists(select 1 from instagram cfg where cfg.model_id=s.model_id and (not cfg.enabled or cfg.reply_mode='off')))) manual_mode,
      coalesce(s.person_id::text,s.channel||':'||s.account_scope||':'||s.external_id) group_key
    from social_contact_summaries s where s.model_id=p_model
      and (coalesce(p_allow_instagram,false) or s.channel<>'instagram')
  ), groups as (
    select group_key,max(last_activity_at) activity from allowed
    group by group_key having bool_or((coalesce(p_channel,'')='' or channel=p_channel) and (coalesce(p_search,'')='' or
      strpos(lower(display_name||' '||username||' '||external_id),lower(p_search))>0)
      and (coalesce(p_filter,'all')='all' or (p_filter='needs_reply' and needs_reply)
        or (p_filter='approvals' and pending_id is not null) or (p_filter='manual' and manual_mode)))
  ), page as (
    select * from groups order by activity desc nulls last,group_key limit greatest(1,least(coalesce(p_limit,30),100)) offset greatest(coalesce(p_offset,0),0)
  ) select jsonb_build_object('total',(select count(*) from groups),'contacts',coalesce((
    select jsonb_agg(to_jsonb(a)-'group_key'-'manual_mode' order by pg.activity desc nulls last,pg.group_key,a.channel,a.external_id)
      from page pg join allowed a using(group_key)),'[]'::jsonb)) into output;
  return output;
end $$;

-- Private helper shared by enqueue and each final boundary. NULL means current.
create function public.social_context_error(p_command public.social_commands) returns text
language plpgsql security definer set search_path=public,pg_temp as $$
declare s record;
begin
  select * into s from social_contact_summaries where model_id=p_command.model_id and channel=p_command.channel and external_id=p_command.external_id and account_scope=p_command.account_scope;
  if not found then return 'contact_or_account_changed'; end if;
  if s.last_message_id is distinct from p_command.expected_source_id then return 'source_changed'; end if;
  if s.identity_id is distinct from p_command.identity_id or s.identity_updated_at is distinct from p_command.identity_updated_at then return 'identity_changed'; end if;
  return null;
end $$;

create function public.social_enqueue(p_model uuid,p_requested_by uuid,p_key uuid,p_operation text,p_channel text,p_external text,p_scope text,p_pending uuid,p_suggestions jsonb,p_source text,p_identity uuid,p_identity_updated_at timestamptz,p_text text,p_brief text)
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
  if p_operation in ('approve','regenerate') and (p_pending is null or p_suggestions is null or jsonb_typeof(p_suggestions)<>'array') then raise exception 'proposal snapshot required'; end if;
  error:=social_context_error(c); if error is not null then raise exception '%',error; end if;
  if p_pending is not null then
    select * into p from pending_replies where model_id=p_model and id=p_pending for update;
    if not found or p.status<>'awaiting' or p.channel<>p_channel or not(p.conv_key=p_external or (p_channel='instagram' and split_part(p.conv_key,':',1)=p_external)) or p.suggestions is distinct from p_suggestions then raise exception 'stale or foreign proposal'; end if;
    if p_operation='approve' and not(p.suggestions @> jsonb_build_array(c.text)) then raise exception 'approved text is not a suggestion'; end if;
  end if;
  insert into social_commands(model_id,requested_by,idempotency_key,operation,channel,external_id,account_scope,pending_id,expected_suggestions,expected_source_id,identity_id,identity_updated_at,text,brief)
    values(p_model,p_requested_by,p_key,p_operation,p_channel,p_external,p_scope,p_pending,p_suggestions,p_source,p_identity,p_identity_updated_at,c.text,c.brief) returning * into c;
  return to_jsonb(c);
end $$;

create function public.social_claim(p_model uuid,p_worker text) returns jsonb
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
  select * into c from social_commands sc where sc.model_id=p_model and sc.status='queued'
    and not exists(select 1 from social_commands busy where busy.model_id=sc.model_id and busy.channel=sc.channel and busy.account_scope=sc.account_scope and busy.external_id=sc.external_id and busy.status in ('working','sending'))
    order by sc.created_at,sc.id for update skip locked limit 1;
  if not found then return null; end if;
  update social_commands set status='working',worker_id=p_worker,lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes',attempts=attempts+1,updated_at=now()
    where id=c.id returning * into c;
  return to_jsonb(c);
end $$;

create function public.social_start_send(p_model uuid,p_command uuid,p_lease uuid,p_worker text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare c social_commands; p pending_replies; error text;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
  if not found then return null; end if;
  select * into c from social_commands where model_id=p_model and id=p_command for update;
  if not found or c.status not in ('working','sending') or c.operation='regenerate' or c.worker_id is distinct from p_worker or c.lease_token is distinct from p_lease or c.lease_until<=now() then return null; end if;
  if exists(select 1 from settings where model_id=p_model and (ai_paused or paused_until>now() or flood_until>now())) then
    update social_commands set status=case when c.status='sending' then 'uncertain' else 'blocked' end,reason='global_pause',updated_at=now(),finished_at=now() where id=c.id;
    return null;
  end if;
  error:=social_context_error(c);
  if c.pending_id is not null then
    select * into p from pending_replies where model_id=p_model and id=c.pending_id for update;
    if not found or p.suggestions is distinct from c.expected_suggestions
      or (c.status='working' and p.status<>'awaiting')
      or (c.status='sending' and (p.status<>'sent' or p.decision_command_id is distinct from c.id)) then error:='proposal_changed'; end if;
  end if;
  if error is not null then
    update social_commands set status=case when c.status='sending' then 'uncertain' else 'stale' end,reason=error,updated_at=now(),finished_at=now() where id=c.id;
    return null;
  end if;
  if c.status='sending' then return to_jsonb(c); end if;
  if c.pending_id is not null then
    update pending_replies set status='sent',decision_command_id=c.id,decided_at=now(),updated_at=now() where model_id=p_model and id=c.pending_id;
  end if;
  update social_commands set status='sending',lease_until=now()+interval '2 minutes',updated_at=now() where id=c.id returning * into c;
  return to_jsonb(c);
end $$;

create function public.social_finish(p_model uuid,p_command uuid,p_lease uuid,p_status text,p_result jsonb,p_reason text) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
declare c social_commands; target text:=p_status;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  if p_status is null or p_status not in ('done','blocked','stale','failed','uncertain') then raise exception 'invalid terminal status'; end if;
  select * into c from social_commands where model_id=p_model and id=p_command for update;
  if not found or c.status not in ('working','sending') or c.lease_token is distinct from p_lease or c.lease_until<=now() then return false; end if;
  perform 1 from models where id=p_model and claimed_by=c.worker_id and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
  if not found then return false; end if;
  if c.status='sending' and p_status in ('blocked','stale','failed') and coalesce(p_result->>'safe_to_retry','false')<>'true' then target:='uncertain'; end if;
  if c.status='working' and p_status='done' and c.operation<>'regenerate' then raise exception 'send boundary required'; end if;
  if c.pending_id is not null and c.status='sending' then
    if target='done' then
      update pending_replies set chosen_text=c.text,kind='text',updated_at=now() where model_id=p_model and id=c.pending_id and status='sent' and decision_command_id=c.id;
    elsif target in ('blocked','stale','failed') then
      update pending_replies set status=case when social_context_error(c) is null and coalesce(p_result->>'restore_pending','true')<>'false' then 'awaiting' else 'superseded' end,
        decision_command_id=null,decided_at=null,updated_at=now()
        where model_id=p_model and id=c.pending_id and status='sent' and decision_command_id=c.id and chosen_text is null;
    end if;
  end if;
  if c.pending_id is not null and c.status='working' and target in ('blocked','stale','failed') and p_result->>'restore_pending'='false' then
    update pending_replies set status='superseded',updated_at=now() where model_id=p_model and id=c.pending_id
      and status='awaiting' and decision_command_id is null and suggestions=c.expected_suggestions;
  end if;
  update social_commands set status=target,result=coalesce(p_result,'{}'),reason=coalesce(p_reason,''),updated_at=now(),finished_at=now() where id=c.id;
  return true;
end $$;

create function public.social_replace_suggestions(p_model uuid,p_pending uuid,p_expected jsonb,p_suggestions jsonb,p_hint text,p_command uuid default null,p_lease uuid default null,p_worker text default null) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
declare c social_commands;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  if p_command is not null then
    perform 1 from models where id=p_model and claimed_by=p_worker and status='active' and heartbeat_at>now()-interval '90 seconds' for share;
    if not found then return false; end if;
    select * into c from social_commands where model_id=p_model and id=p_command for update;
    if not found or c.status<>'working' or c.operation<>'regenerate' or c.pending_id is distinct from p_pending or c.expected_suggestions is distinct from p_expected
      or c.worker_id is distinct from p_worker or c.lease_token is distinct from p_lease or c.lease_until<=now() or social_context_error(c) is not null then return false; end if;
  end if;
  if p_suggestions is null or jsonb_typeof(p_suggestions)<>'array' or jsonb_array_length(p_suggestions)=0 or exists(select 1 from jsonb_array_elements(p_suggestions) v where jsonb_typeof(v)<>'string') then raise exception 'invalid suggestions'; end if;
  update pending_replies set suggestions=p_suggestions,hint=left(coalesce(p_hint,''),300),updated_at=now()
    where model_id=p_model and id=p_pending and status='awaiting' and decision_command_id is null and suggestions=p_expected;
  return found;
end $$;

create function public.social_set_takeover(p_model uuid,p_channel text,p_external text,p_takeover boolean) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
declare changed boolean;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  if p_takeover is null then raise exception 'explicit takeover required'; end if;
  if p_channel='telegram' then
    update dm_users set human_takeover=p_takeover,ai_enabled=case when p_takeover then ai_enabled else true end where model_id=p_model and tg_id::text=p_external;
  elsif p_channel='fanvue' then
    update fv_users set human_takeover=p_takeover,ai_enabled=case when p_takeover then ai_enabled else true end where model_id=p_model and fan_uuid=p_external;
  elsif p_channel='instagram' then
    update ig_users set human_takeover=p_takeover,ai_enabled=case when p_takeover then ai_enabled else true end where model_id=p_model and igsid=p_external;
  else raise exception 'invalid channel'; end if;
  changed:=found;
  if changed and p_takeover then
    update pending_replies set status='superseded',updated_at=now() where model_id=p_model and channel=p_channel and status='awaiting'
      and (conv_key=p_external or (p_channel='instagram' and split_part(conv_key,':',1)=p_external));
    if p_channel='telegram' then update dm_users set pending_reply=false,reply_after=null where model_id=p_model and tg_id::text=p_external; end if;
    if p_channel='instagram' then
      update instagram_actions set state='cancelled',reason='takeover' where model_id=p_model and igsid=p_external and state in ('pending','approval','ready','leased')
        and coalesce(payload->>'origin','')<>'operator';
    end if;
  end if;
  return changed;
end $$;

create function public.social_invalidate_identity_commands() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
begin
  -- Pairing can change the private context of identities whose own person_id
  -- did not change. Version every affected member for final sending rechecks.
  update conversation_identities set updated_at=clock_timestamp()
    where model_id=new.model_id and id<>new.id and person_id in(old.person_id,new.person_id);
  update social_commands c set status='stale',reason='identity_changed',updated_at=now(),finished_at=now()
    where c.model_id=new.model_id and c.status in ('queued','working') and exists(
      select 1 from conversation_identities i where i.model_id=new.model_id and (i.id=new.id or i.person_id in(old.person_id,new.person_id))
        and c.channel=i.platform and c.external_id=i.external_id and (c.channel<>'instagram' or c.account_scope=i.account_scope));
  return new;
end $$;
create trigger social_invalidate_identity_commands after update of person_id,status,candidate_id on public.conversation_identities
  for each row when(old.person_id is distinct from new.person_id or old.status is distinct from new.status or old.candidate_id is distinct from new.candidate_id)
  execute function public.social_invalidate_identity_commands();

-- Existing IG skip trigger records a terminal action, preventing recovery replay.
create function public.social_skip_pending(p_model uuid,p_pending uuid,p_expected jsonb) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  update pending_replies set status='skipped',decided_at=now(),updated_at=now()
    where model_id=p_model and id=p_pending and status='awaiting' and decision_command_id is null and suggestions=p_expected;
  return found;
end $$;

-- All newly introduced APIs, including helpers, are service only.
do $$ declare fn regprocedure; begin
  for fn in select oid::regprocedure from pg_proc where pronamespace='public'::regnamespace and proname in
    ('social_skip_pending','social_context_error','social_enqueue','social_claim','social_start_send','social_finish','social_replace_suggestions','social_set_takeover','social_inbox','social_invalidate_identity_commands') loop
    execute format('revoke all on function %s from public,anon,authenticated',fn);
    execute format('grant execute on function %s to service_role',fn);
  end loop;
end $$;

-- Operator sends retain all source, connection, consent, window and budget checks.
create or replace function public.instagram_reserve(p_model uuid,p_action uuid,p_lease uuid,p_text text,p_link boolean default false,p_reminder boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions; cfg instagram; u ig_users; deny text:=''; floor_day timestamptz;
  h int; d int; r int; last_at timestamptz; identity_person uuid; contact_ids text[]; link_target text; url_cap int; url_gap interval; operator_send boolean:=false;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into strict a from instagram_actions where model_id=p_model and id=p_action for update;
  if a.state<>'leased' or a.lease_token is distinct from p_lease or a.lease_until<=now() then return jsonb_build_object('ok',false,'reason','stale_lease'); end if;
  select * into strict cfg from instagram where model_id=p_model;
  -- A caller-supplied origin flag is insufficient: the exact immutable command,
  -- current worker lease and context must all agree at the reservation boundary.
  select exists(select 1 from social_commands c join models m on m.id=c.model_id
    where c.model_id=p_model and c.id::text=a.payload->>'command_id' and a.payload->>'origin'='operator'
      and c.channel='instagram' and c.external_id=a.igsid and c.account_scope=cfg.ig_user_id
      and c.operation in ('approve','send_text') and c.text=p_text and a.kind='dm'
      and c.status='sending' and c.lease_until>now() and c.worker_id=m.claimed_by
      and m.status='active' and m.heartbeat_at>now()-interval '90 seconds'
      and social_context_error(c) is null) into operator_send;
  if a.payload->>'origin'='operator' and not operator_send then
    update instagram_actions set state='blocked',reason='operator_command_stale' where model_id=p_model and id=a.id;
    return jsonb_build_object('ok',false,'reason','operator_command_stale');
  end if;
  floor_day:=date_trunc('day',now() at time zone 'America/Los_Angeles') at time zone 'America/Los_Angeles';
  if not cfg.connected or ((not cfg.enabled or cfg.reply_mode='off') and not operator_send) then deny:='channel_off';
  elsif coalesce(a.payload->>'account_id','')<>cfg.ig_user_id then deny:='account_changed';
  elsif cfg.circuit_until>now() then deny:='provider_pause';
  elsif exists(select 1 from settings where model_id=p_model and (ai_paused or paused_until>now() or flood_until>now())) then deny:='global_pause';
  elsif exists(select 1 from models where id=p_model and status<>'active') then deny:='model_inactive';
  elsif a.expires_at<=now() then deny:='window_expired';
  elsif not operator_send and cfg.reply_mode='semi' and coalesce(a.payload->>'approved_source_mid','')<>a.source_mid then deny:='approval_required';
  elsif a.kind='comment' and (not cfg.reply_comments or cfg.reply_mode<>'auto') then deny:='comments_off';
  elsif a.kind='reaction' and not cfg.reactions_enabled then deny:='reactions_off';
  elsif a.kind='photo' and not cfg.photos_enabled then deny:='photos_off';
  elsif a.kind='photo' and not exists(select 1 from photos where model_id=p_model and id::text=a.payload->>'photo_id' and url=a.payload->>'photo_url' and active and not spicy and instagram_approved) then deny:='photo_unavailable';
  elsif a.source_at is null or a.source_at>now() then deny:='invalid_source_time';
  elsif a.kind in ('dm','comment') and (btrim(p_text)='' or octet_length(p_text)>case when a.kind='comment' then 300 else 1000 end) then deny:='invalid_text';
  end if;
  if a.kind<>'comment' then
    select * into u from ig_users where model_id=p_model and igsid=a.igsid;
    if not found then deny:='unknown_contact';
    elsif (u.human_takeover or not u.ai_enabled) and not operator_send then deny:='takeover';
    elsif u.no_initiate and not(a.kind='dm' and coalesce(a.payload->>'requested_reply','')='true') then deny:='contact_opt_out';
    elsif a.kind='photo' and (u.no_links or u.age_state not in ('adult_self_declared','adult_platform_verified')) then deny:='photo_not_allowed';
    elsif u.last_source_mid<>a.source_mid then deny:='stale_context';
    elsif u.last_incoming_at is null or u.last_incoming_at>now() or u.last_incoming_at<=now()-interval '24 hours' then deny:='window_expired';
    elsif (p_link or p_reminder) and (u.no_links or u.no_initiate or u.age_state not in ('adult_self_declared','adult_platform_verified')) then deny:='invitation_not_allowed';
    end if;
  end if;
  select person_id into identity_person from conversation_identities where model_id=p_model and platform='instagram' and external_id=a.igsid and account_scope=cfg.ig_user_id limit 1;
  select array_agg(external_id) into contact_ids from conversation_identities where model_id=p_model and platform='instagram' and person_id=identity_person;
  contact_ids:=coalesce(contact_ids,array[a.igsid]);
  if exists(select 1 from conversation_people where model_id=p_model and id=identity_person and no_initiate
    and not(a.kind='dm' and coalesce(a.payload->>'requested_reply','')='true' and a.source_at>stopped_at)) then deny:='contact_opt_out'; end if;
  if a.kind='photo' and exists(select 1 from conversation_people where model_id=p_model and id=identity_person and (no_links or no_initiate or age_state='minor_or_conflicting')) then deny:='photo_not_allowed'; end if;
  if (p_link or p_reminder) and exists(select 1 from conversation_people where model_id=p_model and id=identity_person and (no_links or no_initiate or age_state='minor_or_conflicting')) then deny:='contact_opt_out'; end if;
  if deny<>'' then
    update instagram_actions set state=case when deny='window_expired' then 'expired' else 'blocked' end,reason=deny where model_id=p_model and id=a.id;
    return jsonb_build_object('ok',false,'reason',deny);
  end if;
  -- Successful, in-flight and uncertain sends all spend quota. Failure is released only after definite non-delivery.
  select count(*) filter(where reserved_at>now()-interval '1 hour'),count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours'),max(reserved_at)
    into h,d,r,last_at from instagram_actions where model_id=p_model and reserved_at is not null;
  if h>=20 or d>=100 or r>=100 then deny:='account_limit';
  elsif last_at>now()-interval '45 seconds' then deny:='action_gap'; end if;
  select count(*) filter(where reserved_at>now()-interval '1 hour'),count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours'),max(reserved_at)
    into h,d,r,last_at from instagram_actions where model_id=p_model and reserved_at is not null and
    case when a.kind in ('dm','photo') then kind in ('dm','photo') else kind=a.kind end;
  if a.kind in ('dm','photo') and (h>=12 or d>=60 or r>=60) then deny:='dm_limit';
  elsif a.kind='comment' and (h>=3 or d>=12 or r>=12 or last_at>now()-interval '10 minutes') then deny:='comment_limit';
  elsif a.kind='reaction' and (h>=10 or d>=40 or r>=40) then deny:='reaction_limit'; end if;
  if a.kind in ('dm','photo') then
    select count(*) filter(where reserved_at>now()-interval '1 hour'),count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours')
    into h,d,r from instagram_actions where model_id=p_model and igsid=any(contact_ids) and kind in ('dm','photo') and reserved_at is not null;
    if h>=8 or d>=20 or r>=20 then deny:='conversation_limit'; end if;
    if not exists(select 1 from instagram_actions where model_id=p_model and igsid=any(contact_ids) and kind in ('dm','photo') and reserved_at>now()-interval '15 minutes')
      and (select count(distinct igsid) from instagram_actions where model_id=p_model and kind in ('dm','photo') and reserved_at>now()-interval '15 minutes')>=3 then deny:='active_chats_limit'; end if;
    if not exists(select 1 from instagram_actions where model_id=p_model and igsid=any(contact_ids) and kind in ('dm','photo') and reserved_at is not null) then
      select count(*) filter(where first_at>=floor_day),count(*) filter(where first_at>now()-interval '24 hours') into d,r
        from (select min(reserved_at) first_at from instagram_actions where model_id=p_model and kind in ('dm','photo') and reserved_at is not null group by igsid) first_contacts;
      if d>=10 or r>=10 then deny:='new_contact_limit'; end if;
    end if;
  elsif a.kind='reaction' then
    select count(*) into r from instagram_actions where model_id=p_model and igsid=any(contact_ids) and kind='reaction' and reserved_at>now()-interval '24 hours';
    if r>=3 then deny:='reaction_contact_limit'; end if;
  end if;
  if not p_link and instagram_has_url(p_text) then deny:='unmarked_url'; end if;
  if p_link then
    link_target:=instagram_classify_link(p_text,cfg.telegram_handle,cfg.bio_link);
    if a.kind<>'dm' or link_target='unknown' or cfg.funnel_target not in ('both',link_target) then deny:='link_target_unavailable'; end if;
    url_cap:=case when link_target='telegram' then 4 else 2 end;
    url_gap:=case when link_target='telegram' then interval '2 hours' else interval '4 hours' end;
    select count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours'),max(reserved_at)
      into d,r,last_at from instagram_actions where model_id=p_model and contains_link and reserved_at is not null
        and coalesce(nullif(payload->>'link_target',''),'unknown') in (link_target,'unknown');
    if d>=url_cap or r>=url_cap or last_at>now()-url_gap then deny:='url_limit'; end if;
    select count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours'),max(reserved_at)
      into d,r,last_at from instagram_actions where model_id=p_model and contains_link and reserved_at is not null;
    if d>=6 or r>=6 or last_at>now()-interval '1 hour' then deny:='url_global_limit'; end if;
    if u.link_sent_at is not null or exists(select 1 from instagram_actions where model_id=p_model and igsid=any(contact_ids) and contains_link and reserved_at is not null) then deny:='url_already_sent'; end if;
  end if;
  if p_reminder then
    select count(*) filter(where reserved_at>now()-interval '24 hours'),count(*) filter(where reserved_at>now()-interval '7 days') into d,r
      from instagram_actions where model_id=p_model and igsid=any(contact_ids) and contains_reminder and reserved_at is not null;
    if d>=1 or r>=2 then deny:='reminder_limit'; end if;
  end if;
  if a.kind='photo' and (u.photo_sent_at is not null or exists(select 1 from instagram_actions where model_id=p_model and igsid=any(contact_ids) and kind='photo' and reserved_at is not null)) then deny:='photo_already_sent'; end if;
  if deny<>'' then
    update instagram_actions set state='pending',due_at=now()+interval '15 minutes',reason=deny,lease_token=null,lease_until=null where model_id=p_model and id=a.id;
    return jsonb_build_object('ok',false,'reason',deny);
  end if;
  update instagram_actions set state='sending',text=p_text,contains_link=p_link,contains_reminder=p_reminder,reserved_at=now(),attempts=attempts+1,lease_until=now()+interval '2 minutes',reason=''
    where model_id=p_model and id=a.id;
  return jsonb_build_object('ok',true);
end $$;

create or replace function public.instagram_reset_automation() returns trigger language plpgsql security definer set search_path=public,pg_temp as $$
begin
  if new.ig_user_id is distinct from old.ig_user_id then
    new.sync_started_at:=null; new.sync_completed_at:=null; new.sync_cursor:=''; new.sync_status:='not_started';
    new.replies_started_at:=null; new.test_igsid:=''; new.test_until:=null;
  elsif new.reply_mode='off' or not new.enabled or not new.connected then
    new.replies_started_at:=null;
  elsif old.reply_mode='off' or not old.enabled or not old.connected then
    new.replies_started_at:=now();
  end if;
  if new.reply_mode='off' or not new.enabled or not new.connected or new.ig_user_id is distinct from old.ig_user_id then
    update instagram_actions set state='cancelled',reason='channel_changed'
      where model_id=new.model_id and state in ('pending','ready','approval','leased')
        and (new.ig_user_id is distinct from old.ig_user_id or not new.connected
          or coalesce(payload->>'origin','')<>'operator');
  end if;
  return new;
end $$;

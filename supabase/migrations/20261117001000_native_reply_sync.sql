-- Provider IDs make Telegram echoes/recovery idempotent. Legacy history remains.
alter table public.dm_messages add column provider_message_id bigint,
  add column account_scope text not null default '',
  add column message_origin text not null default 'legacy';
create unique index dm_messages_provider_unique on public.dm_messages(model_id,tg_id,account_scope,provider_message_id)
  where provider_message_id is not null;
alter table public.pending_replies add column source_message_id bigint;
-- Durable catch-up cursor: imported head pages must not conceal an older gap
-- after a worker restart. Existing tenant/service grants remain unchanged.
alter table public.fv_users add column history_sync_state jsonb;

-- Cancel only the obsolete work, never change an explicit takeover or a send
-- already beyond its external boundary. Source-version fences protect that send.
create function public.social_native_reply(p_model uuid,p_channel text,p_external text,p_scope text,p_occurred_at timestamptz)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare incoming timestamptz; current_scope text;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  if p_channel='telegram' then
    select case when coalesce(m.tg_session_enc,'')<>'' then 'telegram:'||md5(m.tg_session_enc) else 'primary' end into current_scope
      from models m join dm_users u on u.model_id=m.id where m.id=p_model and u.tg_id=p_external::bigint;
  elsif p_channel='fanvue' then
    select case when coalesce(c.creator_uuid,'')<>'' then 'fanvue:'||c.creator_uuid else 'primary' end into current_scope
      from fv_users u left join fanvue c on c.model_id=u.model_id where u.model_id=p_model and u.fan_uuid=p_external;
  elsif p_channel='instagram' then
    select c.ig_user_id into current_scope from instagram c join ig_users u on u.model_id=c.model_id
      where c.model_id=p_model and u.igsid=p_external;
  else return false; end if;
  if not found or current_scope is distinct from p_scope then return false; end if;
  if p_channel='telegram' then
    select max(created_at) into incoming from dm_messages where model_id=p_model and tg_id=p_external::bigint and role='user';
    update dm_users set last_reply_at=greatest(last_reply_at,p_occurred_at),
      pending_reply=case when p_occurred_at is null or incoming is null or incoming<=p_occurred_at then false else pending_reply end
      where model_id=p_model and tg_id=p_external::bigint;
  elsif p_channel='fanvue' then
    select max(occurred_at) into incoming from fv_messages where model_id=p_model and fan_uuid=p_external and role='user';
    update fv_users set last_reply_at=greatest(last_reply_at,p_occurred_at) where model_id=p_model and fan_uuid=p_external;
  elsif p_channel='instagram' then
    select max(occurred_at) into incoming from ig_messages where model_id=p_model and igsid=p_external and role='user';
    update ig_users set last_reply_at=greatest(last_reply_at,p_occurred_at) where model_id=p_model and igsid=p_external;
  else return false; end if;
  update pending_replies set status='superseded',updated_at=now()
    where model_id=p_model and channel=p_channel and status='awaiting'
      and (conv_key=p_external or (p_channel='instagram' and split_part(conv_key,':',1)=p_external))
      and (p_occurred_at is null or created_at<=p_occurred_at or incoming is null or incoming<=p_occurred_at);
  update social_commands set status='stale',reason='native_reply',finished_at=now(),updated_at=now()
    where model_id=p_model and channel=p_channel and external_id=p_external and account_scope=p_scope
      and status in ('queued','working')
      and (p_occurred_at is null or created_at<=p_occurred_at or incoming is null or incoming<=p_occurred_at);
  return true;
end $$;
revoke all on function public.social_native_reply(uuid,text,text,text,timestamptz) from public,anon,authenticated;
grant execute on function public.social_native_reply(uuid,text,text,text,timestamptz) to service_role;

create function public.social_ingest_telegram(p_model uuid,p_external bigint,p_message_id bigint,p_scope text,p_role text,p_content text,p_occurred_at timestamptz,p_origin text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare found_id bigint; inserted boolean:=false; scope_value text; legacy_id bigint;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select 'telegram:'||md5(tg_session_enc) into scope_value from models where id=p_model and coalesce(tg_session_enc,'')<>'';
  if scope_value is null or scope_value is distinct from p_scope then raise exception 'telegram account changed'; end if;
  if p_message_id is null or p_message_id<=0 or p_role is null or p_role not in ('user','assistant')
    or p_origin is null or p_origin not in ('native','telepipe') or p_occurred_at is null then raise exception 'invalid provider message'; end if;
  select id into found_id from dm_messages where model_id=p_model and tg_id=p_external and account_scope=p_scope and provider_message_id=p_message_id;
  if found_id is not null then return jsonb_build_object('id',found_id,'inserted',false); end if;
  -- Attach an ID only to one exact legacy text+role in a narrow time window.
  -- Empty/media placeholders are deliberately not content-deduplicated.
  if coalesce(p_content,'')<>'' and left(p_content,1)<>'[' then
    select id into legacy_id from dm_messages where model_id=p_model and tg_id=p_external and provider_message_id is null
      and account_scope='' and role=p_role and content=p_content
      and created_at between p_occurred_at-interval '5 seconds' and p_occurred_at+interval '5 seconds'
      order by abs(extract(epoch from created_at-p_occurred_at)),id limit 1 for update;
  end if;
  if legacy_id is not null then
    update dm_messages set provider_message_id=p_message_id,account_scope=p_scope where id=legacy_id;
    found_id:=legacy_id;
  else
    insert into dm_messages(model_id,tg_id,role,content,created_at,provider_message_id,account_scope,message_origin)
      values(p_model,p_external,p_role,coalesce(p_content,''),p_occurred_at,p_message_id,p_scope,p_origin) returning id into found_id;
    inserted:=true;
  end if;
  if p_role='assistant' and p_origin='native' then
    perform social_native_reply(p_model,'telegram',p_external::text,p_scope,p_occurred_at);
  end if;
  return jsonb_build_object('id',found_id,'inserted',inserted);
end $$;
revoke all on function public.social_ingest_telegram(uuid,bigint,bigint,text,text,text,timestamptz,text) from public,anon,authenticated;
grant execute on function public.social_ingest_telegram(uuid,bigint,bigint,text,text,text,timestamptz,text) to service_role;

-- The imported reply and cancellation commit together; a crash between Python
-- awaits cannot leave a stale proposal available for approval.
create function public.social_imported_reply() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare scope_value text;
begin
  if new.role<>'assistant' then return new; end if;
  if tg_table_name='fv_messages' then
    select case when coalesce(creator_uuid,'')<>'' then 'fanvue:'||creator_uuid else 'primary' end into scope_value from fanvue where model_id=new.model_id;
    perform social_native_reply(new.model_id,'fanvue',new.fan_uuid,scope_value,new.occurred_at);
  elsif tg_table_name='ig_messages' then
    select ig_user_id into scope_value from instagram where model_id=new.model_id;
    perform social_native_reply(new.model_id,'instagram',new.igsid,scope_value,new.occurred_at);
  end if;
  return new;
end $$;
revoke all on function public.social_imported_reply() from public,anon,authenticated;
create trigger social_imported_fanvue_reply after insert on public.fv_messages for each row execute function public.social_imported_reply();
create trigger social_imported_instagram_reply after insert on public.ig_messages for each row execute function public.social_imported_reply();

create function public.social_pending_source_guard() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare version bigint; external_value text;
begin
  if new.source_message_id is null then return new; end if;
  perform pg_advisory_xact_lock(hashtextextended(new.model_id::text,0));
  external_value:=case when new.channel='instagram' then split_part(new.conv_key,':',1) else new.conv_key end;
  select coalesce(last_message_id::bigint,0) into version from social_contact_summaries
    where model_id=new.model_id and channel=new.channel and external_id=external_value;
  if version is distinct from new.source_message_id then return null; end if;
  if new.channel='instagram' and not exists(select 1 from instagram_actions a where a.model_id=new.model_id
    and a.id::text=split_part(new.conv_key,':',2) and a.igsid=external_value and a.state='approval') then return null; end if;
  update pending_replies set status='superseded',updated_at=now()
    where model_id=new.model_id and channel=new.channel and status='awaiting'
      and (conv_key=external_value or (new.channel='instagram' and split_part(conv_key,':',1)=external_value));
  return new;
end $$;
revoke all on function public.social_pending_source_guard() from public,anon,authenticated;
create trigger social_pending_source_guard before insert on public.pending_replies for each row execute function public.social_pending_source_guard();

-- Even a late historical import changes what a draft was based on. Timestamp
-- chronology alone cannot certify that its context is still complete.
create function public.social_message_context_changed() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare channel_value text; external_value text; version bigint; invalidated integer; latest_role text;
begin
  perform pg_advisory_xact_lock(hashtextextended(new.model_id::text,0));
  if tg_table_name='dm_messages' then
    channel_value:='telegram'; external_value:=new.tg_id::text;
    select max(id) into version from dm_messages where model_id=new.model_id and tg_id=new.tg_id;
  elsif tg_table_name='fv_messages' then
    channel_value:='fanvue'; external_value:=new.fan_uuid;
    select max(id) into version from fv_messages where model_id=new.model_id and fan_uuid=new.fan_uuid;
  else
    channel_value:='instagram'; external_value:=new.igsid;
    select max(id) into version from ig_messages where model_id=new.model_id and igsid=new.igsid;
  end if;
  update pending_replies set status='superseded',updated_at=now()
    where model_id=new.model_id and channel=channel_value and status='awaiting'
      and (conv_key=external_value or (channel_value='instagram' and split_part(conv_key,':',1)=external_value))
      and (source_message_id is null or source_message_id<>version);
  get diagnostics invalidated = row_count;
  if channel_value='telegram' and invalidated>0 then
    select role into latest_role from dm_messages where model_id=new.model_id and tg_id=new.tg_id
      order by created_at desc,id desc limit 1;
    if latest_role='user' then
      update dm_users set pending_reply=true where model_id=new.model_id and tg_id=new.tg_id;
    end if;
  end if;
  update social_commands set status='stale',reason='source_changed',finished_at=now(),updated_at=now()
    where model_id=new.model_id and channel=channel_value and external_id=external_value
      and status in ('queued','working') and expected_source_id is distinct from version::text;
  return new;
end $$;
revoke all on function public.social_message_context_changed() from public,anon,authenticated;
create trigger social_message_context_changed after insert on public.dm_messages for each row execute function public.social_message_context_changed();
create trigger social_message_context_changed after insert on public.fv_messages for each row execute function public.social_message_context_changed();
create trigger social_message_context_changed after insert on public.ig_messages for each row execute function public.social_message_context_changed();

-- Existing installations can contain historical duplicates. Preserve them,
-- while preventing new duplicates from concurrent sends, polling and retries.
create index fv_messages_provider_lookup on public.fv_messages(model_id,fan_uuid,message_uuid)
  where message_uuid is not null and message_uuid<>'';
create function public.social_fanvue_message_dedup() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
begin
  if coalesce(new.message_uuid,'')='' then return new; end if;
  perform pg_advisory_xact_lock(hashtextextended(new.model_id::text,0));
  if exists(select 1 from fv_messages where model_id=new.model_id and fan_uuid=new.fan_uuid and message_uuid=new.message_uuid) then return null; end if;
  return new;
end $$;
revoke all on function public.social_fanvue_message_dedup() from public,anon,authenticated;
create trigger social_fanvue_message_dedup before insert on public.fv_messages for each row execute function public.social_fanvue_message_dedup();

-- Regeneration upgrades legacy proposals to the guarded context revision.
create or replace function public.social_replace_suggestions(p_model uuid,p_pending uuid,p_expected jsonb,p_suggestions jsonb,p_hint text,p_command uuid default null,p_lease uuid default null,p_worker text default null) returns boolean
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
  update pending_replies set suggestions=p_suggestions,hint=left(coalesce(p_hint,''),300),updated_at=now(),
    source_message_id=case when p_command is not null then coalesce(c.expected_source_id::bigint,0) else source_message_id end
    where model_id=p_model and id=p_pending and status='awaiting' and decision_command_id is null and suggestions=p_expected;
  return found;
end $$;

-- A changed context can invalidate the web draft while its newer Instagram
-- inbound still needs a reply. Requeue only orphaned, undecided approvals.
create function public.instagram_requeue_stale_approval(p_model uuid,p_igsid text,p_source_mid text,p_source_message_id bigint)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions; cfg instagram; current_version bigint; latest ig_messages;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into cfg from instagram where model_id=p_model;
  if not found or not cfg.connected or not cfg.enabled or cfg.reply_mode<>'semi' then return false; end if;
  if exists(select 1 from ig_users where model_id=p_model and igsid=p_igsid and (human_takeover or not ai_enabled)) then return false; end if;
  select max(id) into current_version from ig_messages where model_id=p_model and igsid=p_igsid;
  if current_version is distinct from p_source_message_id then return false; end if;
  select * into latest from ig_messages where model_id=p_model and igsid=p_igsid order by occurred_at desc nulls last,id desc limit 1;
  if not found or latest.role<>'user' or latest.mid is distinct from p_source_mid then return false; end if;
  select * into a from instagram_actions where model_id=p_model and igsid=p_igsid and source_mid=p_source_mid
    and state='approval' and reserved_at is null and coalesce(payload->>'origin','')<>'operator'
    and payload->>'account_id'=cfg.ig_user_id order by created_at desc limit 1 for update;
  if not found then return false; end if;
  if exists(select 1 from pending_replies where model_id=p_model and channel='instagram' and conv_key=p_igsid||':'||a.id::text
    and status in ('awaiting','skipped','sent')) then return false; end if;
  if exists(select 1 from social_commands c join pending_replies p on p.model_id=c.model_id and p.id=c.pending_id
    where c.model_id=p_model and c.status in ('queued','working','sending') and p.channel='instagram' and p.conv_key=p_igsid||':'||a.id::text) then return false; end if;
  update instagram_actions set state='pending',due_at=now(),text='',reason='history_changed',lease_token=null,lease_until=null,
    payload=payload-'approved_source_mid'-'approved_intent' where model_id=p_model and id=a.id;
  return true;
end $$;
revoke all on function public.instagram_requeue_stale_approval(uuid,text,text,bigint) from public,anon,authenticated;
grant execute on function public.instagram_requeue_stale_approval(uuid,text,text,bigint) to service_role;

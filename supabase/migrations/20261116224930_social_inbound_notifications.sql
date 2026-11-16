-- A control bot is an inbound-notification endpoint. Provider sends and all
-- operator decisions remain in Social sites. Never backfill the old inbox.
alter table public.control_bot_settings add column notify_social_inbound boolean not null default true;
grant insert(notify_social_inbound),update(notify_social_inbound) on public.control_bot_settings to authenticated;
create table public.social_notification_rollout (
  singleton boolean primary key default true check(singleton),
  started_at timestamptz not null default clock_timestamp()
);
insert into public.social_notification_rollout(singleton) values(true);
create table public.social_notifications (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references public.models(id) on delete cascade,
  channel text not null check(channel in ('telegram','fanvue','instagram')),
  external_id text not null,
  account_scope text not null,
  source_key text not null,
  source_at timestamptz not null,
  preview text not null,
  received_at timestamptz not null default clock_timestamp(),
  consumed_at timestamptz,
  unique(model_id,channel,external_id,account_scope,source_key)
);
create index social_notifications_pending on public.social_notifications(model_id,received_at)
  where consumed_at is null;
alter table public.social_notification_rollout enable row level security;
alter table public.social_notifications enable row level security;
revoke all on public.social_notification_rollout,public.social_notifications from public,anon,authenticated;
grant select on public.social_notification_rollout to service_role;
grant select,insert,update,delete on public.social_notifications to service_role;

-- Read the effective channel/contact mode and current provider connection.
-- Called both at ingestion and at dispatch so Auto/reconnect never leaks a
-- delayed alert. No conversation history or provider seen state is changed.
create function public.social_notification_route(p_model uuid,p_channel text,p_external text) returns jsonb
language plpgsql stable security definer set search_path=public,pg_temp as $$
declare m models; scope_value text; name_value text; mode_value text; manual_value boolean;
begin
  select * into m from models where id=p_model and status='active' and model_type='persona';
  if not found or m.owner_chat_id is null or coalesce(m.control_bot_token_enc,'')='' then return null; end if;
  if not coalesce((select notify_social_inbound from control_bot_settings where model_id=p_model),true) then return null; end if;
  if p_channel='telegram' then
    if coalesce(m.tg_session_enc,'')='' then return null; end if;
    scope_value:='telegram:'||md5(m.tg_session_enc);
    select coalesce(nullif(u.first_name,''),nullif(u.username,''),u.tg_id::text),s.tg_reply_mode,
      u.human_takeover or not u.ai_enabled into name_value,mode_value,manual_value
      from dm_users u join settings s on s.model_id=u.model_id where u.model_id=p_model and u.tg_id::text=p_external;
  elsif p_channel='fanvue' then
    select 'fanvue:'||f.creator_uuid,coalesce(nullif(u.display_name,''),nullif(u.handle,''),u.fan_uuid),
      case when f.enabled then f.reply_mode else 'off' end,u.human_takeover or not u.ai_enabled
      into scope_value,name_value,mode_value,manual_value
      from fv_users u join fanvue f on f.model_id=u.model_id
      where u.model_id=p_model and u.fan_uuid=p_external and f.connected and f.creator_uuid<>'';
  elsif p_channel='instagram' then
    if not exists(select 1 from accounts where id=m.account_id and role='superadmin') then return null; end if;
    select cfg.ig_user_id,coalesce(nullif(u.name,''),nullif(u.username,''),u.igsid),
      case when cfg.enabled then cfg.reply_mode else 'off' end,u.human_takeover or not u.ai_enabled
      into scope_value,name_value,mode_value,manual_value
      from ig_users u join instagram cfg on cfg.model_id=u.model_id
      where u.model_id=p_model and u.igsid=p_external and cfg.connected and cfg.ig_user_id<>'';
  end if;
  if scope_value is null or mode_value is null or (mode_value not in ('off','semi') and not coalesce(manual_value,false)) then return null; end if;
  return jsonb_build_object('account_scope',scope_value,'display_name',left(name_value,80),'owner_chat_id',m.owner_chat_id);
end $$;

create function public.social_queue_inbound_notification() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare channel_value text; external_value text; source_value timestamptz; key_value text; route jsonb;
begin
  if new.role<>'user' then return new; end if;
  if tg_table_name='dm_messages' then
    channel_value:='telegram'; external_value:=new.tg_id::text;
    source_value:=new.created_at; key_value:='row:'||new.id::text;
  elsif tg_table_name='fv_messages' then
    channel_value:='fanvue'; external_value:=new.fan_uuid;
    source_value:=new.occurred_at; key_value:=case when coalesce(new.message_uuid,'')<>'' then 'provider:'||new.message_uuid else 'row:'||new.id::text end;
  elsif tg_table_name='ig_messages' then
    channel_value:='instagram'; external_value:=new.igsid;
    source_value:=new.occurred_at; key_value:=case when coalesce(new.mid,'')<>'' then 'provider:'||new.mid else 'row:'||new.id::text end;
  else return new;
  end if;
  if source_value is null or source_value<now()-interval '24 hours' or source_value>now()+interval '1 minute'
    or source_value<(select started_at from social_notification_rollout where singleton) then return new; end if;
  route:=social_notification_route(new.model_id,channel_value,external_value);
  if route is null then return new; end if;
  insert into social_notifications(model_id,channel,external_id,account_scope,source_key,source_at,preview)
    values(new.model_id,channel_value,external_value,route->>'account_scope',key_value,source_value,
      left(regexp_replace(new.content,'\s+',' ','g'),180)) on conflict do nothing;
  return new;
exception when others then
  -- Notifications are best effort. Never roll back the authoritative chat
  -- history because the secondary doorbell queue is unavailable or invalid.
  raise warning 'Social inbound notification skipped (SQLSTATE %)',sqlstate;
  return new;
end $$;
create trigger social_notify_telegram after insert on public.dm_messages for each row execute function public.social_queue_inbound_notification();
create trigger social_notify_fanvue after insert on public.fv_messages for each row execute function public.social_queue_inbound_notification();
create trigger social_notify_instagram after insert on public.ig_messages for each row execute function public.social_queue_inbound_notification();

create function public.social_notification_claim(p_model uuid,p_worker text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare batch record; latest social_notifications; route jsonb; batch_count integer;
begin
  perform 1 from models where id=p_model and claimed_by=p_worker and status='active'
    and heartbeat_at>now()-interval '90 seconds' and owner_chat_id is not null and control_bot_token_enc<>'' for share;
  if not found then return null; end if;
  perform pg_advisory_xact_lock(hashtextextended('social-notifications:'||p_model::text,0));
  -- Retain dedupe longer than the maximum accepted source age.
  delete from social_notifications where model_id=p_model and consumed_at<now()-interval '7 days';
  update social_notifications set consumed_at=now() where model_id=p_model and consumed_at is null and source_at<now()-interval '24 hours';
  for batch in
    select channel,external_id,account_scope,min(received_at) first_at,max(received_at) last_at
      from social_notifications where model_id=p_model and consumed_at is null
      group by channel,external_id,account_scope
      having max(received_at)<=now()-interval '8 seconds' or min(received_at)<=now()-interval '60 seconds'
      order by min(received_at) limit 50
  loop
    route:=social_notification_route(p_model,batch.channel,batch.external_id);
    -- Include precisely the batch observed here. An inbound INSERT racing the
    -- claim is a new event for the following batch, never overwritten/lost.
    with consumed as (
      update social_notifications set consumed_at=clock_timestamp()
        where model_id=p_model and channel=batch.channel and external_id=batch.external_id and account_scope=batch.account_scope
          and consumed_at is null and received_at<=batch.last_at returning *
    ) select count(*) into batch_count from consumed;
    if route is null or route->>'account_scope' is distinct from batch.account_scope then continue; end if;
    select * into latest from social_notifications where model_id=p_model and channel=batch.channel
      and external_id=batch.external_id and account_scope=batch.account_scope and received_at between batch.first_at and batch.last_at
      order by source_at desc,received_at desc,id desc limit 1;
    return jsonb_build_object('id',latest.id,'channel',latest.channel,'external_id',latest.external_id,
      'account_scope',latest.account_scope,'display_name',route->>'display_name','owner_chat_id',route->'owner_chat_id',
      'preview',latest.preview,'message_count',batch_count,'last_incoming_at',latest.source_at);
  end loop;
  return null;
end $$;
revoke all on function public.social_notification_route(uuid,text,text),public.social_queue_inbound_notification(),public.social_notification_claim(uuid,text) from public,anon,authenticated;
grant execute on function public.social_notification_route(uuid,text,text),public.social_notification_claim(uuid,text) to service_role;

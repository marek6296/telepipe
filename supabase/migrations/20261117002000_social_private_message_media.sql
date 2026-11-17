-- Incoming media is private. Only the service worker and owner-authorized server read it.
create table public.social_message_media (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references public.models(id) on delete cascade,
  channel text not null check(channel in ('telegram','instagram','fanvue')),
  external_id text not null, account_scope text not null,
  message_id bigint not null, attachment_key text not null, provider_message_id text not null,
  kind text not null check(kind in ('audio','video','image','file')),
  mime_type text, storage_path text, transcript text, description text,
  duration_seconds double precision check(duration_seconds>=0 and duration_seconds<=180),
  status text not null default 'pending' check(status in ('pending','processing','ready','unavailable','failed')),
  error text, original_content text not null,
  attempts integer not null default 0, lease_token uuid, lease_until timestamptz,
  retry_after timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(model_id,channel,account_scope,message_id,attachment_key),
  check(storage_path is null or storage_path like model_id::text||'/'||channel||'/'||message_id::text||'/'||id::text||'.%')
);
create index social_message_media_contact on public.social_message_media(model_id,channel,external_id,account_scope,message_id);
alter table public.social_message_media enable row level security;
revoke all on public.social_message_media from public,anon,authenticated;
grant all on public.social_message_media to service_role;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('social-media','social-media',false,41943040,array['audio/mpeg','video/mp4','image/jpeg'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
-- No storage.objects policy: authenticated clients receive only server-issued short-lived signed URLs.

-- Semantic updates consume the SAME channel sequence as new messages. IDs stay
-- stable. INSERT also allocates after the lock: its serial ID may have been
-- reserved before a concurrent media finalization obtained that lock.
alter table public.dm_messages add column context_version bigint;
alter table public.fv_messages add column context_version bigint;
alter table public.ig_messages add column context_version bigint;
create function public.social_message_revision() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.model_id::text,0));
  new.context_version:=nextval(pg_get_serial_sequence(tg_table_schema||'.'||tg_table_name,'id'));
  return new;
end $$;
create trigger social_media_dm_revision before insert or update of content,created_at on public.dm_messages
  for each row execute function public.social_message_revision();
create trigger social_media_fv_revision before insert or update of content,occurred_at on public.fv_messages
  for each row execute function public.social_message_revision();
create trigger social_media_ig_revision before insert or update of content,occurred_at on public.ig_messages
  for each row execute function public.social_message_revision();
revoke all on function public.social_message_revision() from public,anon,authenticated;

create or replace view public.social_contact_summaries with(security_invoker=true) as
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
  select model_id,'telegram'::text channel,tg_id::text external_id,id,greatest(id,coalesce(context_version,id)) revision,role,content,created_at source_at,created_at ingestion_at from public.dm_messages
  union all
  select model_id,'fanvue',fan_uuid,id,greatest(id,coalesce(context_version,id)) revision,role,content,occurred_at,created_at from public.fv_messages
  union all
  select model_id,'instagram',igsid,id,greatest(id,coalesce(context_version,id)) revision,role,content,occurred_at,created_at from public.ig_messages
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
left join lateral (select msg.*,max(msg.revision) over() context_id from messages msg where msg.model_id=c.model_id and msg.channel=c.channel and msg.external_id=c.external_id
  order by msg.source_at desc nulls last,msg.id desc limit 1) m on true
left join lateral (select pr.id from public.pending_replies pr where pr.model_id=c.model_id and pr.channel=c.channel and pr.status='awaiting'
  and (pr.conv_key=c.external_id or (c.channel='instagram' and split_part(pr.conv_key,':',1)=c.external_id))
  order by pr.created_at desc,pr.id desc limit 1) p on true;

create or replace function public.social_message_context_changed() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare channel_value text; external_value text; version bigint; invalidated integer; latest_role text;
begin
  perform pg_advisory_xact_lock(hashtextextended(new.model_id::text,0));
  if tg_table_name='dm_messages' then
    channel_value:='telegram'; external_value:=new.tg_id::text;
    select max(greatest(id,coalesce(context_version,id))) into version from dm_messages where model_id=new.model_id and tg_id=new.tg_id;
  elsif tg_table_name='fv_messages' then
    channel_value:='fanvue'; external_value:=new.fan_uuid;
    select max(greatest(id,coalesce(context_version,id))) into version from fv_messages where model_id=new.model_id and fan_uuid=new.fan_uuid;
  else
    channel_value:='instagram'; external_value:=new.igsid;
    select max(greatest(id,coalesce(context_version,id))) into version from ig_messages where model_id=new.model_id and igsid=new.igsid;
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
create or replace function public.instagram_requeue_stale_approval(p_model uuid,p_igsid text,p_source_mid text,p_source_message_id bigint)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions; cfg instagram; current_version bigint; latest ig_messages;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into cfg from instagram where model_id=p_model;
  if not found or not cfg.connected or not cfg.enabled or cfg.reply_mode<>'semi' then return false; end if;
  if exists(select 1 from ig_users where model_id=p_model and igsid=p_igsid and (human_takeover or not ai_enabled)) then return false; end if;
  select max(greatest(id,coalesce(context_version,id))) into current_version from ig_messages where model_id=p_model and igsid=p_igsid;
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
create trigger social_media_dm_context after update of content,created_at on public.dm_messages
  for each row execute function public.social_message_context_changed();
create trigger social_media_fv_context after update of content,occurred_at on public.fv_messages
  for each row execute function public.social_message_context_changed();
create trigger social_media_ig_context after update of content,occurred_at on public.ig_messages
  for each row execute function public.social_message_context_changed();

create function public.social_media_claim(p_model uuid,p_channel text,p_external text,p_scope text,p_provider_id text,p_attachment text,p_kind text,p_occurred_at timestamptz default null,p_role text default null)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare tab text; ext text; provider text; stamp_col text; message_record record; item social_message_media; original text; scope_value text; legacy_id bigint; legacy_count integer;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select account_scope into scope_value from social_contact_summaries where model_id=p_model and channel=p_channel and external_id=p_external;
  if scope_value is distinct from p_scope then return null; end if;
  if p_channel='telegram' then tab:='dm_messages'; ext:='tg_id'; provider:='provider_message_id'; stamp_col:='created_at';
  elsif p_channel='fanvue' then tab:='fv_messages'; ext:='fan_uuid'; provider:='message_uuid'; stamp_col:='occurred_at';
  elsif p_channel='instagram' then tab:='ig_messages'; ext:='igsid'; provider:='mid'; stamp_col:='occurred_at';
  else return null; end if;
  execute format('select id,content,%I occurred_at from public.%I where model_id=$1 and %I::text=$2 and %I::text=$3 %s order by id desc limit 1',stamp_col,tab,ext,provider,case when p_channel='telegram' then 'and account_scope=$4' else '' end)
    into message_record using p_model,p_external,p_provider_id,p_scope;
  if message_record.id is null and p_channel='telegram' and p_occurred_at is not null and p_role in ('user','assistant') then
    -- Old Telegram history predates durable provider IDs. Bind only an
    -- unambiguous exact timestamp+role row; never create a duplicate turn.
    select count(*),min(id) into legacy_count,legacy_id from dm_messages
      where model_id=p_model and tg_id::text=p_external and provider_message_id is null
        and account_scope='' and role=p_role and created_at=p_occurred_at;
    if legacy_count=1 then
      update dm_messages set provider_message_id=p_provider_id::bigint,account_scope=p_scope
        where id=legacy_id and model_id=p_model;
      select id,content,created_at occurred_at into message_record from dm_messages where id=legacy_id;
    end if;
  end if;
  if message_record.id is null then return null; end if;
  select original_content into original from social_message_media where model_id=p_model and channel=p_channel and account_scope=p_scope and message_id=message_record.id order by created_at,id limit 1;
  insert into social_message_media(model_id,channel,external_id,account_scope,message_id,attachment_key,provider_message_id,kind,original_content)
    values(p_model,p_channel,p_external,p_scope,message_record.id,p_attachment,p_provider_id,p_kind,coalesce(original,message_record.content)) on conflict do nothing;
  select * into item from social_message_media where model_id=p_model and channel=p_channel and account_scope=p_scope and message_id=message_record.id and attachment_key=p_attachment for update;
  if item.status in ('ready','unavailable') or item.attempts>=3 or item.lease_until>now() or item.retry_after>now() then return null; end if;
  if message_record.occurred_at is null or message_record.occurred_at<now()-interval '7 days' then
    update social_message_media set status='unavailable',error='history_limit',updated_at=now() where id=item.id;
    return null;
  end if;
  update social_message_media set status='processing',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes',attempts=attempts+1,updated_at=now() where id=item.id returning * into item;
  return to_jsonb(item);
end $$;

create function public.social_media_finish(p_model uuid,p_id uuid,p_lease uuid,p_result jsonb)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare item social_message_media; tab text; scope_value text; content_value text; path_value text;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into item from social_message_media where model_id=p_model and id=p_id and status='processing' and lease_token=p_lease and lease_until>now() for update;
  if not found then return false; end if;
  select account_scope into scope_value from social_contact_summaries where model_id=p_model and channel=item.channel and external_id=item.external_id;
  if scope_value is distinct from item.account_scope then return false; end if;
  if p_result->>'status' not in ('ready','failed','unavailable') then raise exception 'invalid media result'; end if;
  path_value:=p_result->>'storage_path';
  if path_value is not null and path_value not in (
    p_model::text||'/'||item.channel||'/'||item.message_id::text||'/'||item.id::text||'.mp3',
    p_model::text||'/'||item.channel||'/'||item.message_id::text||'/'||item.id::text||'.mp4',
    p_model::text||'/'||item.channel||'/'||item.message_id::text||'/'||item.id::text||'.jpg') then raise exception 'invalid storage path'; end if;
  if coalesce(p_result->>'error','') !~ '^[a-z_]*$' then raise exception 'invalid media error'; end if;
  update social_message_media set status=p_result->>'status',error=p_result->>'error',
    storage_path=coalesce(path_value,storage_path),mime_type=coalesce(p_result->>'mime_type',mime_type),
    transcript=coalesce(nullif(left(p_result->>'transcript',6000),''),transcript),
    description=coalesce(nullif(left(p_result->>'description',3000),''),description),
    duration_seconds=coalesce((p_result->>'duration_seconds')::double precision,duration_seconds),
    lease_until=null,lease_token=null,retry_after=now()+interval '10 minutes',updated_at=now()
    where id=p_id;
  -- Both readers consume these exact strings. Never insert a fake user turn.
  select item.original_content||coalesce(string_agg(
    E'\n[Attachment '||kind||': '||status||']'||
    case when transcript is not null then E'\nTranscript: '||transcript else '' end||
    case when description is not null then E'\nVisual description (sampled frames): '||description else '' end||
    case when error is not null then E'\nAnalysis unavailable: '||error else '' end,
    E'\n' order by created_at,id),'') into content_value
    from social_message_media where model_id=p_model and channel=item.channel and account_scope=item.account_scope and message_id=item.message_id;
  tab:=case item.channel when 'telegram' then 'dm_messages' when 'instagram' then 'ig_messages' else 'fv_messages' end;
  execute format('update public.%I set content=$1 where model_id=$2 and id=$3 and content is distinct from $1',tab) using content_value,p_model,item.message_id;
  return true;
end $$;
revoke all on function public.social_media_claim(uuid,text,text,text,text,text,text,timestamptz,text) from public,anon,authenticated;
revoke all on function public.social_media_finish(uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.social_media_claim(uuid,text,text,text,text,text,text,timestamptz,text) to service_role;
grant execute on function public.social_media_finish(uuid,uuid,uuid,jsonb) to service_role;

create or replace function public.social_ingest_telegram(p_model uuid,p_external bigint,p_message_id bigint,p_scope text,p_role text,p_content text,p_occurred_at timestamptz,p_origin text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare found_id bigint; inserted boolean:=false; scope_value text; legacy_id bigint;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select 'telegram:'||md5(tg_session_enc) into scope_value from models where id=p_model and coalesce(tg_session_enc,'')<>'';
  if scope_value is null or scope_value is distinct from p_scope then raise exception 'telegram account changed'; end if;
  if p_message_id is null or p_message_id<=0 or p_role is null or p_role not in ('user','assistant')
    or p_origin is null or p_origin not in ('native','telepipe') or p_occurred_at is null then raise exception 'invalid provider message'; end if;
  select id into found_id from dm_messages where model_id=p_model and tg_id=p_external and account_scope=p_scope and provider_message_id=p_message_id;
  if found_id is not null then return jsonb_build_object('id',found_id,'inserted',false,'source_version',(select greatest(id,coalesce(context_version,id)) from dm_messages where model_id=p_model and id=found_id)); end if;
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
  return jsonb_build_object('id',found_id,'inserted',inserted,'source_version',(select greatest(id,coalesce(context_version,id)) from dm_messages where model_id=p_model and id=found_id));
end $$;

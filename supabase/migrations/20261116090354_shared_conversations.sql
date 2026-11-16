-- Shared conversation state. All writes/RPCs are server-only; owner UI reads via RLS.
create table public.conversation_people (
  model_id uuid not null references public.models(id) on delete cascade,
  id uuid not null default gen_random_uuid(),
  no_initiate boolean not null default false,
  no_links boolean not null default false,
  age_state text not null default 'unknown' check (age_state in ('unknown','adult_self_declared','adult_platform_verified','minor_or_conflicting')),
  created_at timestamptz not null default now(),
  primary key (model_id,id)
);

create table public.conversation_identities (
  model_id uuid not null references public.models(id) on delete cascade,
  id uuid not null default gen_random_uuid(),
  person_id uuid not null,
  platform text not null check (platform in ('telegram','instagram','fanvue')),
  account_scope text not null default 'primary',
  external_id text not null check (external_id <> ''),
  username text not null default '', display_name text not null default '',
  status text not null default 'local' check (status in ('local','candidate','recognized','verified')),
  candidate_id uuid,
  rejected_ids uuid[] not null default '{}',
  evidence jsonb not null default '{}',
  last_invite_at timestamptz, invite_target text,
  updated_at timestamptz not null default now(),
  primary key (model_id,id),
  unique (model_id,platform,account_scope,external_id),
  foreign key (model_id,person_id) references public.conversation_people(model_id,id),
  foreign key (model_id,candidate_id) references public.conversation_identities(model_id,id)
);
create index conversation_identities_person on public.conversation_identities(model_id,person_id);

create table public.conversation_link_audit (
  model_id uuid not null references public.models(id) on delete cascade,
  id bigint generated always as identity primary key,
  identity_id uuid not null, other_identity_id uuid,
  event text not null, evidence jsonb not null default '{}',
  created_at timestamptz not null default now(),
  foreign key(model_id,identity_id) references public.conversation_identities(model_id,id)
);

create table public.conversation_days (
  model_id uuid not null references public.models(id) on delete cascade,
  local_day date not null, timezone text not null,
  plan jsonb not null, mood text not null,
  created_at timestamptz not null default now(),
  primary key(model_id,local_day)
);

create table public.instagram_actions (
  model_id uuid not null references public.models(id) on delete cascade,
  id uuid not null default gen_random_uuid(),
  dedupe_key text not null,
  kind text not null check (kind in ('dm','comment','reaction','photo')),
  igsid text not null default '', target_id text not null,
  source_mid text not null default '', source_at timestamptz,
  due_at timestamptz not null, expires_at timestamptz not null,
  state text not null default 'pending' check (state in ('pending','approval','ready','leased','sending','sent','uncertain','cancelled','expired','blocked','skipped')),
  payload jsonb not null default '{}',
  text text not null default '',
  contains_link boolean not null default false,
  contains_reminder boolean not null default false,
  lease_token uuid, lease_until timestamptz, reserved_at timestamptz,
  attempts int not null default 0,
  reason text not null default '', provider_id text,
  created_at timestamptz not null default now(), sent_at timestamptz,
  primary key(model_id,id), unique(model_id,dedupe_key),
  check (expires_at > source_at or source_at is null)
);
create index instagram_actions_due on public.instagram_actions(model_id,state,due_at);
create index instagram_actions_budget on public.instagram_actions(model_id,reserved_at) where reserved_at is not null;

alter table public.instagram
  add column sync_enabled boolean not null default false,
  add column sync_started_at timestamptz,
  add column sync_completed_at timestamptz,
  add column sync_cursor text not null default '',
  add column sync_status text not null default 'not_started',
  add column replies_started_at timestamptz,
  add column reactions_enabled boolean not null default false,
  add column photos_enabled boolean not null default false,
  add column highlights_link boolean not null default false,
  add column typo_enabled boolean not null default false,
  add column test_igsid text not null default '',
  add column test_until timestamptz,
  add column circuit_until timestamptz,
  add column circuit_reason text not null default '';
alter table public.ig_users
  add column last_source_mid text not null default '',
  add column no_links boolean not null default false,
  add column no_initiate boolean not null default false,
  add column age_state text not null default 'unknown',
  add column photo_sent_at timestamptz,
  add column link_sent_at timestamptz,
  add column last_reminder_at timestamptz,
  add column last_typo jsonb;
alter table public.ig_messages
  add column occurred_at timestamptz,
  add column source text not null default 'legacy',
  add column metadata jsonb not null default '{}';
create index ig_messages_time on public.ig_messages(model_id,igsid,occurred_at desc nulls last,id desc);

-- Helpers never accept a caller-supplied clock. DB time is authoritative for send quotas.
create function public.conversation_ensure_identity(p_model uuid,p_platform text,p_external text,p_scope text default 'primary',p_username text default '',p_name text default '')
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare i conversation_identities; p uuid;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into i from conversation_identities where model_id=p_model and platform=p_platform and external_id=p_external and account_scope=p_scope;
  if not found then
    insert into conversation_people(model_id) values(p_model) returning id into p;
    insert into conversation_identities(model_id,person_id,platform,external_id,account_scope,username,display_name)
    values(p_model,p,p_platform,p_external,p_scope,p_username,p_name) returning * into i;
  else
    update conversation_identities set username=coalesce(nullif(p_username,''),username),display_name=coalesce(nullif(p_name,''),display_name),updated_at=now()
    where model_id=p_model and id=i.id returning * into i;
  end if;
  return to_jsonb(i);
end $$;

create function public.conversation_pair(p_model uuid,p_identity uuid,p_other uuid,p_decision text,p_evidence jsonb default '{}')
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare i conversation_identities; other conversation_identities; fresh uuid; old_person uuid;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into strict i from conversation_identities where model_id=p_model and id=p_identity for update;
  if p_decision not in ('candidate','recognized','verified','rejected') then raise exception 'invalid decision'; end if;
  if p_decision='rejected' then
    old_person:=i.person_id;
    insert into conversation_people(model_id,no_initiate,no_links,age_state)
      select p_model,no_initiate,no_links,age_state from conversation_people where model_id=p_model and id=i.person_id returning id into fresh;
    update conversation_identities set person_id=fresh,status='local',candidate_id=null,evidence='{}',
      rejected_ids=array_append(rejected_ids,coalesce(p_other,i.candidate_id)),updated_at=now()
      where model_id=p_model and id=i.id returning * into i;
    -- Pending context for every IG identity affected by the old group must be regenerated.
    update instagram_actions set state='cancelled',reason='identity_changed'
      where model_id=p_model and state in ('pending','ready','approval','leased') and igsid in
      (select external_id from conversation_identities where model_id=p_model and platform='instagram' and (person_id=old_person or id=p_identity));
  else
    select * into strict other from conversation_identities where model_id=p_model and id=p_other;
    if i.id=other.id or p_other=any(i.rejected_ids) then raise exception 'invalid association'; end if;
    if p_decision='verified' then
      -- Only owner action/challenge completion calls this decision; worker heuristics never do.
      update conversation_people set no_initiate=no_initiate or (select no_initiate from conversation_people where model_id=p_model and id=i.person_id),
        no_links=no_links or (select no_links from conversation_people where model_id=p_model and id=i.person_id),
        age_state=case when age_state='minor_or_conflicting' or (select age_state from conversation_people where model_id=p_model and id=i.person_id)='minor_or_conflicting' then 'minor_or_conflicting' else age_state end
        where model_id=p_model and id=other.person_id;
      update conversation_identities set person_id=other.person_id,status='verified',updated_at=now() where model_id=p_model and person_id=i.person_id;
      update conversation_identities set status='verified' where model_id=p_model and id=other.id;
    end if;
    update conversation_identities set candidate_id=p_other,status=p_decision,evidence=p_evidence,updated_at=now()
      where model_id=p_model and id=i.id returning * into i;
    update instagram_actions set state='cancelled',reason='identity_changed'
      where model_id=p_model and state in ('pending','ready','approval','leased') and igsid in
      (select external_id from conversation_identities where model_id=p_model and platform='instagram' and person_id in(i.person_id,other.person_id));
  end if;
  insert into conversation_link_audit(model_id,identity_id,other_identity_id,event,evidence) values(p_model,p_identity,p_other,p_decision,p_evidence);
  return to_jsonb(i);
end $$;

create function public.instagram_enqueue(p_model uuid,p_key text,p_kind text,p_igsid text,p_target text,p_source_mid text,p_source_at timestamptz,p_due timestamptz,p_expires timestamptz,p_payload jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  if p_kind in ('dm','reaction','photo') then
    update instagram_actions set state='cancelled',reason='newer_input'
    where model_id=p_model and igsid=p_igsid and kind in ('dm','reaction','photo')
      and state in ('pending','ready','approval','leased') and source_mid<>p_source_mid
      and source_at<=p_source_at;
  end if;
  insert into instagram_actions(model_id,dedupe_key,kind,igsid,target_id,source_mid,source_at,due_at,expires_at,payload)
  values(p_model,p_key,p_kind,p_igsid,p_target,p_source_mid,p_source_at,p_due,p_expires,p_payload)
  on conflict(model_id,dedupe_key) do nothing returning * into a;
  if not found then select * into a from instagram_actions where model_id=p_model and dedupe_key=p_key; end if;
  return to_jsonb(a);
end $$;

create function public.instagram_claim(p_model uuid)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  update instagram_actions set state='uncertain',reason='send_lease_expired'
    where model_id=p_model and state='sending' and lease_until<now();
  update instagram_actions set state='pending',lease_token=null,lease_until=null
    where model_id=p_model and state='leased' and lease_until<now();
  update instagram_actions set state='expired',reason='window_expired'
    where model_id=p_model and state in ('pending','ready','approval','leased') and expires_at<=now();
  select * into a from instagram_actions where model_id=p_model and state in ('pending','ready') and due_at<=now()
    order by case when kind in ('dm','photo') then 0 else 1 end,due_at for update skip locked limit 1;
  if not found then return null; end if;
  update instagram_actions set state='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes'
    where model_id=p_model and id=a.id returning * into a;
  return to_jsonb(a);
end $$;

create function public.instagram_reserve(p_model uuid,p_action uuid,p_lease uuid,p_text text,p_link boolean default false,p_reminder boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions; cfg instagram; u ig_users; deny text:=''; floor_day timestamptz;
  h int; d int; r int; last_at timestamptz; identity_person uuid; contact_ids text[];
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into strict a from instagram_actions where model_id=p_model and id=p_action for update;
  if a.state<>'leased' or a.lease_token is distinct from p_lease or a.lease_until<=now() then return jsonb_build_object('ok',false,'reason','stale_lease'); end if;
  select * into strict cfg from instagram where model_id=p_model;
  floor_day:=date_trunc('day',now() at time zone 'America/Los_Angeles') at time zone 'America/Los_Angeles';
  if not cfg.connected or not cfg.enabled or cfg.reply_mode='off' then deny:='channel_off';
  elsif coalesce(a.payload->>'account_id','')<>cfg.ig_user_id then deny:='account_changed';
  elsif cfg.circuit_until>now() then deny:='provider_pause';
  elsif exists(select 1 from settings where model_id=p_model and (ai_paused or paused_until>now())) then deny:='global_pause';
  elsif exists(select 1 from models where id=p_model and status<>'active') then deny:='model_inactive';
  elsif a.expires_at<=now() then deny:='window_expired';
  elsif a.kind='comment' and (not cfg.reply_comments or cfg.reply_mode<>'auto') then deny:='comments_off';
  elsif a.kind='reaction' and not cfg.reactions_enabled then deny:='reactions_off';
  elsif a.kind='photo' and not cfg.photos_enabled then deny:='photos_off';
  elsif a.source_at is null or a.source_at>now() then deny:='invalid_source_time';
  elsif a.kind in ('dm','comment') and (btrim(p_text)='' or octet_length(p_text)>case when a.kind='comment' then 300 else 1000 end) then deny:='invalid_text';
  end if;
  if a.kind<>'comment' then
    select * into u from ig_users where model_id=p_model and igsid=a.igsid;
    if not found then deny:='unknown_contact';
    elsif u.human_takeover or not u.ai_enabled then deny:='takeover';
    elsif u.last_source_mid<>a.source_mid then deny:='stale_context';
    elsif u.last_incoming_at is null or u.last_incoming_at>now() or u.last_incoming_at<=now()-interval '24 hours' then deny:='window_expired';
    elsif (p_link or p_reminder) and (u.no_links or u.no_initiate or u.age_state not in ('adult_self_declared','adult_platform_verified')) then deny:='invitation_not_allowed';
    end if;
  end if;
  select person_id into identity_person from conversation_identities where model_id=p_model and platform='instagram' and external_id=a.igsid and account_scope=cfg.ig_user_id limit 1;
  select array_agg(external_id) into contact_ids from conversation_identities where model_id=p_model and platform='instagram' and person_id=identity_person;
  contact_ids:=coalesce(contact_ids,array[a.igsid]);
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
  if p_link then
    select count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours'),max(reserved_at)
      into d,r,last_at from instagram_actions where model_id=p_model and contains_link and reserved_at is not null;
    if d>=2 or r>=2 or last_at>now()-interval '4 hours' then deny:='url_limit'; end if;
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

create function public.instagram_finish(p_model uuid,p_action uuid,p_lease uuid,p_outcome text,p_provider text default '',p_reason text default '')
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_model::text,0));
  select * into a from instagram_actions where model_id=p_model and id=p_action for update;
  if not found or a.lease_token is distinct from p_lease or a.state not in ('sending','uncertain') then return false; end if;
  if p_outcome not in ('sent','uncertain','failed') then raise exception 'invalid outcome'; end if;
  update instagram_actions set state=case when p_outcome='failed' then 'blocked' else p_outcome end,
    reserved_at=case when p_outcome='failed' then null else reserved_at end,
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

do $$
declare t text; f record;
begin
  foreach t in array array['conversation_people','conversation_identities','conversation_link_audit','conversation_days','instagram_actions'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from anon,authenticated',t);
    execute format('grant all on public.%I to service_role',t);
    execute format('grant select on public.%I to authenticated',t);
    execute format('create policy owner_read on public.%I for select to authenticated using (model_id in (select id from public.models where account_id=(select auth.uid())))',t);
  end loop;
  for f in select p.oid::regprocedure as signature from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in
    ('conversation_ensure_identity','conversation_pair','instagram_enqueue','instagram_claim','instagram_reserve','instagram_finish') loop
    execute format('revoke all on function %s from public,anon,authenticated',f.signature);
    execute format('grant execute on function %s to service_role',f.signature);
  end loop;
end $$;
grant select(sync_enabled,sync_started_at,sync_completed_at,sync_cursor,sync_status,replies_started_at,reactions_enabled,photos_enabled,highlights_link,typo_enabled,test_igsid,test_until,circuit_until,circuit_reason) on public.instagram to authenticated;
grant update(sync_enabled,reactions_enabled,photos_enabled,highlights_link,typo_enabled) on public.instagram to authenticated;
grant usage,select on sequence public.conversation_link_audit_id_seq to service_role;

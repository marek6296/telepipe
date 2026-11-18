-- Explicit owner sending uses configured destinations, not Auto age/funnel eligibility.
create or replace function public.instagram_reserve(p_model uuid,p_action uuid,p_lease uuid,p_text text,p_link boolean default false,p_reminder boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare a instagram_actions; cfg instagram; u ig_users; deny text:=''; floor_day timestamptz;
  h int; d int; r int; last_at timestamptz; identity_person uuid; contact_ids text[]; link_target text; url_cap int; url_gap interval; operator_send boolean:=false; owner_fanvue boolean:=false;
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
  owner_fanvue:=operator_send and instagram_configured_fanvue(p_model,p_text);
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
    elsif (p_link or p_reminder) and (u.no_links or u.no_initiate or (not operator_send and u.age_state not in ('adult_self_declared','adult_platform_verified'))) then deny:='invitation_not_allowed';
    end if;
  end if;
  select person_id into identity_person from conversation_identities where model_id=p_model and platform='instagram' and external_id=a.igsid and account_scope=cfg.ig_user_id limit 1;
  select array_agg(external_id) into contact_ids from conversation_identities where model_id=p_model and platform='instagram' and person_id=identity_person;
  contact_ids:=coalesce(contact_ids,array[a.igsid]);
  if exists(select 1 from conversation_people where model_id=p_model and id=identity_person and no_initiate
    and not(a.kind='dm' and coalesce(a.payload->>'requested_reply','')='true' and a.source_at>stopped_at)) then deny:='contact_opt_out'; end if;
  if a.kind='photo' and exists(select 1 from conversation_people where model_id=p_model and id=identity_person and (no_links or no_initiate or age_state='minor_or_conflicting')) then deny:='photo_not_allowed'; end if;
  if (p_link or p_reminder) and exists(select 1 from conversation_people where model_id=p_model and id=identity_person and (no_links or no_initiate or (not operator_send and age_state='minor_or_conflicting'))) then deny:='contact_opt_out'; end if;
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
    link_target:=case when owner_fanvue then 'fanvue' else instagram_classify_link(p_text,cfg.telegram_handle,cfg.bio_link) end;
    if a.kind<>'dm' or link_target='unknown' or (not operator_send and cfg.funnel_target not in ('both',link_target)) then deny:='link_target_unavailable'; end if;
    url_cap:=case when link_target='telegram' then 4 else 2 end;
    url_gap:=case when link_target='telegram' then interval '2 hours' else interval '4 hours' end;
    select count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours'),max(reserved_at)
      into d,r,last_at from instagram_actions where model_id=p_model and contains_link and reserved_at is not null
        and coalesce(nullif(payload->>'link_target',''),'unknown') in (link_target,'unknown');
    if d>=url_cap or r>=url_cap or last_at>now()-url_gap then deny:='url_limit'; end if;
    select count(*) filter(where reserved_at>=floor_day),count(*) filter(where reserved_at>now()-interval '24 hours'),max(reserved_at)
      into d,r,last_at from instagram_actions where model_id=p_model and contains_link and reserved_at is not null;
    if d>=6 or r>=6 or last_at>now()-interval '1 hour' then deny:='url_global_limit'; end if;
    if not operator_send and (u.link_sent_at is not null or exists(select 1 from instagram_actions where model_id=p_model and igsid=any(contact_ids) and contains_link and reserved_at is not null)) then deny:='url_already_sent'; end if;
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

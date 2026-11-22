-- Changing to Auto resumes current unanswered Semi drafts, not their wording.
-- Explicit owner deliveries/takeovers are preserved. Normal worker gates still
-- decide freshness, schedule, provider window, consent and quotas before sending.
create function public.social_resume_auto_pending() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare channel_name text; mode_key text; p record; source record; resumed boolean;
begin
 channel_name:=case tg_table_name when 'settings' then 'telegram' else tg_table_name end;
 mode_key:=case channel_name when 'telegram' then 'tg_reply_mode' else 'reply_mode' end;
 if to_jsonb(new)->>mode_key is distinct from 'auto'
   or to_jsonb(old)->>mode_key is not distinct from 'auto' then return new;end if;
 perform pg_advisory_xact_lock(hashtextextended(new.model_id::text,0));
 for p in select pr.* from pending_replies pr
   join social_contact_summaries s on s.model_id=pr.model_id and s.channel=pr.channel
     and s.external_id=split_part(pr.conv_key,':',1) and s.last_message_id=pr.source_message_id::text
   where pr.model_id=new.model_id and pr.channel=channel_name and pr.status='awaiting'
     and not exists(select 1 from social_commands c where c.model_id=pr.model_id and c.channel=pr.channel
       and c.external_id=split_part(pr.conv_key,':',1) and c.operation<>'regenerate'
       and c.status in ('queued','working','sending','uncertain'))
   for update of pr
 loop
  resumed:=false;
  if channel_name='instagram' then
   update instagram_actions a set state='pending',text='',due_at=now(),reason='mode_changed_to_auto',
     lease_token=null,lease_until=null,payload=a.payload-'approved_intent'-'approved_source_mid'
    where a.model_id=new.model_id and a.id::text=split_part(p.conv_key,':',2)
     and a.state='approval' and a.kind='dm' and a.reserved_at is null and a.provider_id is null
     and a.expires_at>now() and a.payload->>'account_id'=new.ig_user_id
     and coalesce(a.payload->>'origin','')<>'operator'
     and exists(select 1 from ig_users u where u.model_id=new.model_id and u.igsid=a.igsid and u.ai_enabled and not u.human_takeover);
   resumed:=found;
  elsif channel_name='telegram' then
   update dm_users u set pending_reply=true
    where u.model_id=new.model_id and u.tg_id::text=p.conv_key and u.ai_enabled and not u.human_takeover
     and u.farewell_at is null and u.last_incoming_at>now()-interval '48 hours'
     and (u.last_reply_at is null or u.last_reply_at<u.last_incoming_at);
   resumed:=found;
  else
   select m.* into source from fv_messages m join fv_users u on u.model_id=m.model_id and u.fan_uuid=m.fan_uuid
    where m.model_id=new.model_id and m.fan_uuid=p.conv_key and u.ai_enabled and not u.human_takeover
    order by m.occurred_at desc nulls last,m.id desc limit 1;
   if found and source.role='user' and source.occurred_at is not null then
    insert into fanvue_events(model_id,event_id,event_type,payload,notified_at)
     values(new.model_id,'auto-resume:'||p.id::text,'creator.message.received',jsonb_build_object('data',jsonb_build_object(
       'fan',jsonb_build_object('uuid',p.conv_key),'sender','fan','text',source.content,
       'uuid',source.message_uuid,'created_at',source.occurred_at)),now()) on conflict do nothing;
    resumed:=true;
   end if;
  end if;
  if resumed then
   update pending_replies set status='superseded',updated_at=now() where model_id=new.model_id and id=p.id and status='awaiting';
  end if;
 end loop;
 return new;
end $$;
revoke all on function public.social_resume_auto_pending() from public,anon,authenticated;
create trigger social_resume_tg_auto after update of tg_reply_mode on public.settings for each row execute function public.social_resume_auto_pending();
create trigger social_resume_ig_auto after update of reply_mode on public.instagram for each row execute function public.social_resume_auto_pending();
create trigger social_resume_fv_auto after update of reply_mode on public.fanvue for each row execute function public.social_resume_auto_pending();

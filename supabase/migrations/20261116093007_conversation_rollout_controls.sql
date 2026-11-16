-- Explicit owner approval of the one normal IG image; existing media stays private.
alter table public.photos add column instagram_approved boolean not null default false;
grant select(instagram_approved),update(instagram_approved) on public.photos to authenticated;

-- Backfill isolated identities, never trust legacy heuristic fv_users.tg_id.
do $$
declare r record; ident jsonb;
begin
  for r in select model_id,tg_id,username,first_name,link_sent_at from dm_users loop
    ident:=conversation_ensure_identity(r.model_id,'telegram',r.tg_id::text,'primary',coalesce(r.username,''),coalesce(r.first_name,''));
    update conversation_identities set last_invite_at=r.link_sent_at,invite_target='fanvue'
      where model_id=r.model_id and id=(ident->>'id')::uuid and last_invite_at is null and r.link_sent_at is not null;
  end loop;
  for r in select model_id,fan_uuid,handle,display_name from fv_users loop
    perform conversation_ensure_identity(r.model_id,'fanvue',r.fan_uuid::text,'primary',coalesce(r.handle,''),coalesce(r.display_name,''));
  end loop;
  for r in select u.model_id,u.igsid,u.username,u.name,i.ig_user_id from ig_users u join instagram i on i.model_id=u.model_id where i.ig_user_id<>'' loop
    perform conversation_ensure_identity(r.model_id,'instagram',r.igsid,r.ig_user_id,coalesce(r.username,''),coalesce(r.name,''));
  end loop;
end $$;

-- Every reconnect or Off transition establishes a fresh automation watermark.
create function public.instagram_reset_automation() returns trigger language plpgsql security definer set search_path=public,pg_temp as $$
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
      where model_id=new.model_id and state in ('pending','ready','approval','leased');
  end if;
  return new;
end $$;
create trigger instagram_reset_automation before update on public.instagram
  for each row execute function public.instagram_reset_automation();
revoke all on function public.instagram_reset_automation() from public,anon,authenticated;

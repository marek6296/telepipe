-- Recover recent unanswered work after channel pause; never replay sent/uncertain or deliberately skipped work.
create or replace function public.instagram_enqueue(p_model uuid,p_key text,p_kind text,p_igsid text,p_target text,p_source_mid text,p_source_at timestamptz,p_due timestamptz,p_expires timestamptz,p_payload jsonb default '{}')
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
  on conflict(model_id,dedupe_key) do update set
    state='pending',reason='',text='',payload=excluded.payload,due_at=excluded.due_at,
    lease_token=null,lease_until=null
  where instagram_actions.state='cancelled' and instagram_actions.reason in ('channel_off','channel_changed')
    and instagram_actions.reserved_at is null and excluded.expires_at>now()
    and excluded.source_at>now()-interval '24 hours' and excluded.source_at<=now()
    and exists(select 1 from instagram i where i.model_id=p_model and i.connected and i.enabled
      and i.reply_mode in ('auto','semi') and i.ig_user_id=p_payload->>'account_id')
  returning * into a;
  if not found then select * into a from instagram_actions where model_id=p_model and dedupe_key=p_key; end if;
  return to_jsonb(a);
end $$;

create or replace function public.instagram_claim(p_model uuid)
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
  select * into a from instagram_actions where model_id=p_model and state in ('pending','ready') and (due_at<=now() or
      (kind='dm' and reason in ('','sleeping') and exists(select 1 from instagram i
        where i.model_id=p_model and i.connected and i.enabled and i.reply_mode='semi')))
    order by case when kind in ('dm','photo') then 0 else 1 end,due_at for update skip locked limit 1;
  if not found then return null; end if;
  update instagram_actions set state='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes'
    where model_id=p_model and id=a.id returning * into a;
  return to_jsonb(a);
end $$;


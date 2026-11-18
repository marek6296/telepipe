-- Automatic polling must never claim/cancel an owner action between release and durable defer.
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
  select * into a from instagram_actions where model_id=p_model and coalesce(payload->>'origin','')<>'operator' and state in ('pending','ready') and (due_at<=now() or
      (kind='dm' and reason in ('','sleeping') and exists(select 1 from instagram i
        where i.model_id=p_model and i.connected and i.enabled and i.reply_mode='semi')))
    order by case when kind in ('dm','photo') then 0 else 1 end,due_at for update skip locked limit 1;
  if not found then return null; end if;
  update instagram_actions set state='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes'
    where model_id=p_model and id=a.id returning * into a;
  return to_jsonb(a);
end $$;

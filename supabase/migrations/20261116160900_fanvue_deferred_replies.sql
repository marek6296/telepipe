-- Keep scheduled replies pending without blocking new owner notifications.
alter table public.fanvue_events
  add column reply_deferred boolean not null default false,
  add column notified_at timestamptz,
  add column payment_recorded_at timestamptz;

create index fanvue_events_new_pending_idx
  on public.fanvue_events (model_id, id)
  where processed_at is null and not reply_deferred;

-- Retrying the thank-you must never charge the same purchase to totals twice.
-- Invoker permissions + service_role-only EXECUTE keep tenant routing internal.
create function public.fanvue_record_payment_once(
  p_model_id uuid, p_event_id bigint, p_fan_uuid text, p_cents integer
) returns jsonb
language plpgsql security invoker set search_path = ''
as $$
declare
  v_recorded timestamptz;
  v_fan public.fv_users%rowtype;
begin
  if p_cents < 0 then
    raise exception 'Payment amount must be nonnegative';
  end if;
  select payment_recorded_at into v_recorded
    from public.fanvue_events
    where model_id = p_model_id and id = p_event_id
    for update;
  if not found then
    raise exception 'Fanvue event not found for model';
  end if;

  if v_recorded is null then
    update public.fv_users
      set spent_cents = spent_cents + p_cents,
          bought_count = bought_count + 1,
          last_bought_at = now(),
          pending_offer_at = null
      where model_id = p_model_id and fan_uuid = p_fan_uuid
      returning * into v_fan;
    if not found then
      raise exception 'Fanvue fan not found for model';
    end if;
    update public.fanvue_events set payment_recorded_at = now()
      where model_id = p_model_id and id = p_event_id;
  else
    select * into v_fan from public.fv_users
      where model_id = p_model_id and fan_uuid = p_fan_uuid;
  end if;
  return to_jsonb(v_fan);
end;
$$;
revoke all on function public.fanvue_record_payment_once(uuid, bigint, text, integer)
  from public, anon, authenticated;
grant execute on function public.fanvue_record_payment_once(uuid, bigint, text, integer)
  to service_role;

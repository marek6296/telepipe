-- Fáza 2 — final review fixes.
--
-- (1) Throttle na `tg_login_jobs`: bez neho vie prihlásený účet tlačiť login
--     joby do fronty donekonečna — zaplaví Telegram SMS kódmi (u operátora to
--     vyzerá ako abuse) a zaťaží zdieľaný worker (DoS pre ostatných tenantov).
--     Web síce staré LIVE_PHASES joby pred vložením zavrie na 'error', ale nič
--     mu nebráni robiť to v cykle. DB tvrdý strop: max 5 jobov / účet / hodinu.
--
-- (2) `usage_events.atlas_cost_usd` je naša nákupná cena (marža). RLS riadok
--     pustí majiteľovi, ale stĺpcový grant mu ho nesmie ukázať — inak si klient
--     dopočíta koľko na ňom zarábame. Web ho aj tak nikdy neselectuje, no
--     obrana musí byť v DB, nie v aplikačnom kóde.

-- ---------------------------------------------------------------------------
-- (1) tg_login_jobs — hodinový strop na počet login pokusov na účet
-- ---------------------------------------------------------------------------

create or replace function tg_login_jobs_throttle()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if (select count(*) from tg_login_jobs
      where account_id = new.account_id
        and created_at > now() - interval '1 hour') >= 5 then
    raise exception 'rate_limit: too many login attempts, try again later';
  end if;
  return new;
end;
$$;

revoke execute on function tg_login_jobs_throttle() from public, anon, authenticated;

create trigger tg_login_jobs_throttle_trg
  before insert on tg_login_jobs
  for each row execute function public.tg_login_jobs_throttle();

-- ---------------------------------------------------------------------------
-- (2) usage_events — skry atlas_cost_usd (marža) pred klientom
-- ---------------------------------------------------------------------------

revoke select on usage_events from authenticated;
grant select (id, model_id, account_id, kind, input_tokens, output_tokens,
              unit_count, charged_usd, created_at)
  on usage_events to authenticated;

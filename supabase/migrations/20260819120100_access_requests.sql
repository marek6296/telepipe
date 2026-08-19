-- Žiadosti o prístup — fronta, ktorú Marek odbavuje z webu alebo z Telegramu.
--
-- ROZHODOVANIE MÁ JEDNO JADRO
-- ---------------------------
-- `decide_access_request(...)` robí prácu a berie herca ako parameter. Nad ním
-- sú dva vstupy:
--   * web      → `admin_decide_access_request(...)`, autorizuje `is_admin()`
--   * Telegram → jadro priamo, service_role (v HTTP requeste z Bot API žiadny
--                `auth.uid()` neexistuje, takže `is_admin()` by tam vždy padlo)
-- Keby mal každý vstup vlastnú kópiu logiky, raz by sa rozišli — a to by
-- znamenalo, že jednou cestou sa schvaľuje inak než druhou.

create table if not exists access_requests (
  id           uuid primary key default gen_random_uuid(),
  account_id   uuid not null references accounts(id) on delete cascade,
  status       text not null default 'pending'
               check (status in ('pending', 'approved', 'rejected')),
  message      text not null default '',
  created_at   timestamptz not null default now(),
  decided_at   timestamptz,
  decided_by   uuid references accounts(id) on delete set null,
  decided_note text not null default ''
);

-- Jeden účet = najviac jedna otvorená žiadosť. Partial index, lebo zamietnutú
-- žiadosť smie podať znova (cooldown zámerne nerobíme — pri desiatkach
-- používateľov je to problém, ktorý neexistuje).
create unique index if not exists access_requests_one_pending
  on access_requests (account_id) where status = 'pending';

create index if not exists access_requests_pending_first
  on access_requests (created_at desc) where status = 'pending';

-- ---------------------------------------------------------------------------
-- RLS — žiadateľ vidí svoje, píše výhradne RPC
-- ---------------------------------------------------------------------------

alter table access_requests enable row level security;
revoke all on access_requests from anon, authenticated;
grant select (id, account_id, status, message, created_at, decided_at, decided_note)
  on access_requests to authenticated;

drop policy if exists access_requests_owner_select on access_requests;
create policy access_requests_owner_select on access_requests
  for select to authenticated using (account_id = (select auth.uid()));

-- Žiadny INSERT/UPDATE/DELETE policy ZÁMERNE: keby si žiadateľ vedel zapísať
-- riadok sám, vedel by si doň napísať `status = 'approved'`.

-- ---------------------------------------------------------------------------
-- request_access — žiadateľ o seba
-- ---------------------------------------------------------------------------
--
-- Idempotentné: opakovaný klik vráti existujúcu otvorenú žiadosť namiesto toho,
-- aby Marekovi nasypal do Telegramu desať správ.

create or replace function request_access(p_message text)
returns uuid language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid := auth.uid();
  v_id uuid;
begin
  if v_account is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  if account_unlocked(v_account) then
    raise exception 'account already unlocked' using errcode = '22023';
  end if;

  select id into v_id from access_requests
   where account_id = v_account and status = 'pending' limit 1;
  if v_id is not null then return v_id; end if;

  insert into access_requests (account_id, message)
  values (v_account, left(coalesce(p_message, ''), 1000))
  returning id into v_id;
  return v_id;
end;
$$;

revoke execute on function request_access(text) from public, anon;
grant execute on function request_access(text) to authenticated;

-- ---------------------------------------------------------------------------
-- decide_access_request — jadro (service_role only)
-- ---------------------------------------------------------------------------
--
-- `p_actor` je admin, ktorý rozhodol — ide do auditu. Schválenie dvíha plán
-- LEN z `free`: keby žiadosť visela účtu, ktorý medzitým dostal `vip`,
-- schválenie by ho nesmelo degradovať.

create or replace function decide_access_request(
  p_id uuid, p_approve boolean, p_note text, p_actor uuid
)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid; v_status text; v_next text;
begin
  select account_id, status into v_account, v_status
    from access_requests where id = p_id for update;
  if v_account is null then raise exception 'request not found'; end if;

  -- Už rozhodnutá žiadosť sa nerozhoduje druhýkrát. Vraciame stav, nie chybu:
  -- Marek môže kliknúť vo webe aj v Telegrame a druhý klik nemá kričať.
  if v_status <> 'pending' then return v_status; end if;

  v_next := case when p_approve then 'approved' else 'rejected' end;

  update access_requests
     set status = v_next,
         decided_at = now(),
         decided_by = p_actor,
         decided_note = left(coalesce(p_note, ''), 500)
   where id = p_id;

  if p_approve then
    insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                    amount, note)
    values (v_account, p_actor,
            coalesce((select email from accounts where id = v_account), ''),
            coalesce((select email from accounts where id = p_actor), ''),
            0, 'access approved -> plan=free_plus');
    update accounts set plan = 'free_plus' where id = v_account and plan = 'free';
  end if;

  return v_next;
end;
$$;

revoke execute on function decide_access_request(uuid, boolean, text, uuid)
  from public, anon, authenticated;
grant execute on function decide_access_request(uuid, boolean, text, uuid) to service_role;

-- ---------------------------------------------------------------------------
-- admin_decide_access_request — webový vstup do jadra
-- ---------------------------------------------------------------------------

create or replace function admin_decide_access_request(
  p_id uuid, p_approve boolean, p_note text default ''
)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  return decide_access_request(p_id, p_approve, p_note, auth.uid());
end;
$$;

revoke execute on function admin_decide_access_request(uuid, boolean, text) from public, anon;
grant execute on function admin_decide_access_request(uuid, boolean, text) to authenticated;

-- ---------------------------------------------------------------------------
-- admin_list_access_requests — pre admin panel
-- ---------------------------------------------------------------------------

create or replace function admin_list_access_requests()
returns table (
  id uuid, account_id uuid, email text, plan text, status text, message text,
  created_at timestamptz, decided_at timestamptz, decided_note text,
  decided_by_email text
)
language sql stable security definer
set search_path = public, pg_temp as $$
  select r.id, r.account_id, a.email, a.plan, r.status, r.message,
         r.created_at, r.decided_at, r.decided_note,
         d.email as decided_by_email
  from access_requests r
  join accounts a on a.id = r.account_id
  left join accounts d on d.id = r.decided_by
  where is_admin()
  order by (r.status = 'pending') desc, r.created_at desc
  limit 500;
$$;

revoke execute on function admin_list_access_requests() from public, anon;
grant execute on function admin_list_access_requests() to authenticated;

-- ---------------------------------------------------------------------------
-- Sonda
-- ---------------------------------------------------------------------------

do $$
declare
  v_probe uuid; v_super uuid;
  v_role_before text; v_plan_before text;
  v_req uuid; v_req2 uuid;
  v_audit_before bigint; v_reqs_before bigint;
  v_idempotent boolean := false;
  v_unlocked_refused boolean := false;
  v_plan_after text;
  v_second text;
  v_direct_write_blocked boolean := false;
  v_nonadmin_blocked boolean := false;
  v_reached boolean := false;
begin
  select id, role, plan into v_probe, v_role_before, v_plan_before
  from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;
  select id into v_super from accounts where role = 'superadmin' order by created_at limit 1;
  select count(*) into v_audit_before from credit_adjustments;
  select count(*) into v_reqs_before from access_requests;

  if v_probe is null or v_super is null then
    raise notice 'access-requests: sonda preskocena — chyba vhodny ucet';
  else
    begin
      update accounts set role = 'user', plan = 'free' where id = v_probe;

      -- (1) Ziadost + idempotencia
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      v_req := request_access('prosim o pristup');
      v_req2 := request_access('druhy klik');
      v_idempotent := (v_req = v_req2);

      -- (2) Ziadatel si NESMIE prepisat status priamo
      begin
        execute 'set local role authenticated';
        begin
          update access_requests set status = 'approved' where id = v_req;
          if not found then v_direct_write_blocked := true; end if;
        exception when others then v_direct_write_blocked := true;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
      end;

      -- (3) Neadmin nesmie rozhodnut
      begin
        perform admin_decide_access_request(v_req, true, '');
      exception when insufficient_privilege then v_nonadmin_blocked := true;
      end;

      -- (4) Superadmin schvali → plan vyskoci na free_plus
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_super)::text, true);
      perform admin_decide_access_request(v_req, true, '');
      select plan into v_plan_after from accounts where id = v_probe;

      -- (5) Druhe rozhodnutie tej istej ziadosti nema nic menit
      v_second := admin_decide_access_request(v_req, false, 'znova');

      -- (6) Odomknuty ucet uz nesmie ziadat
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        perform request_access('este raz');
      exception when others then v_unlocked_refused := true;
      end;

      v_reached := true;
      raise exception 'access-requests-sonda-rollback' using errcode = 'P0001';
    exception when raise_exception then
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then raise exception 'access-requests: sonda spadla skor, nez dobehla'; end if;
    if not v_idempotent then raise exception 'access-requests: druhy klik zalozil druhu ziadost'; end if;
    if not v_direct_write_blocked then raise exception 'access-requests: ZIADATEL SI SAM SCHVALIL ZIADOST'; end if;
    if not v_nonadmin_blocked then raise exception 'access-requests: neadmin dokazal rozhodnut'; end if;
    if v_plan_after <> 'free_plus' then raise exception 'access-requests: schvalenie nedvihlo plan (je %)', v_plan_after; end if;
    if v_second <> 'approved' then raise exception 'access-requests: druhe rozhodnutie prepisalo prve (%)', v_second; end if;
    if not v_unlocked_refused then raise exception 'access-requests: odomknuty ucet dokazal poziadat znova'; end if;

    if (select count(*) from access_requests) <> v_reqs_before then
      raise exception 'access-requests: sonda po sebe nechala ziadosti';
    end if;
    if (select count(*) from credit_adjustments) <> v_audit_before then
      raise exception 'access-requests: sonda po sebe nechala audit riadky';
    end if;
    if exists (
      select 1 from accounts
      where id = v_probe and (role <> v_role_before or plan <> v_plan_before)
    ) then
      raise exception 'access-requests: sonda po sebe nechala zmeneny ucet';
    end if;
  end if;
end $$;

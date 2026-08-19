-- Prístup na pozvanie — tretí balík `free_plus` (v UI „Standard+").
--
-- PREČO
-- -----
-- Registrácia je otvorená, ale pracovať smie až ten, koho Marek schváli. Balík
-- je nosičom toho povolenia, lebo Marek ho spravuje v tom istom dropdowne
-- v admin paneli, kde dnes prepína Standard/VIP.
--
-- ČO SA TU ZÁMERNE NEMENÍ
-- -----------------------
-- * `record_usage` — vetví sa iba na `'vip'` (021), takže `free_plus` padne do
--   vetvy `else` a účtuje sa PRESNE ako `free` dnes. Fakturácie sa nedotýkame.
--   Sonda nižšie ten predpoklad kontroluje priamo v tele funkcie.
-- * Existujúce účty — Mareka odomyká rola, kamaráta plán `vip`. Žiadny presun
--   dát netreba; zámok platí len na účty vzniknuté odteraz.
-- * `models` SELECT/UPDATE/DELETE — kto už modelku má a plán mu vezmú, nesmie
--   o dáta prísť. Zamkne sa mu web, nie databáza.

-- ---------------------------------------------------------------------------
-- (a) accounts.plan — whitelist v schéme
-- ---------------------------------------------------------------------------
--
-- Meno constraintu ostáva rovnaké (konvencia z 021/024), aby sa v `pg_constraint`
-- nehromadili historické verzie.

alter table accounts drop constraint if exists accounts_plan_check;
alter table accounts
  add constraint accounts_plan_check
  check (plan in ('free', 'free_plus', 'vip'));

-- ---------------------------------------------------------------------------
-- (b) account_unlocked() — JEDINÝ zdroj pravdy o odomknutí
-- ---------------------------------------------------------------------------
--
-- Volá ju RLS aj aplikácia (`web/lib/access.ts`). Keby pravidlo žilo na dvoch
-- miestach nezávisle, raz by sa rozišlo — a to tiché rozídenie by bola diera,
-- nie chyba zobrazenia.
--
-- `security definer`, lebo `authenticated` má na `accounts` column-scoped granty
-- a RLS; funkcia musí vedieť prečítať plán aj rolu ľubovoľného účtu.

create or replace function account_unlocked(p_account uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
  select exists (
    select 1 from accounts
    where id = p_account
      and (plan in ('free_plus', 'vip') or role in ('admin', 'superadmin'))
  );
$$;

revoke execute on function account_unlocked(uuid) from public, anon;
grant execute on function account_unlocked(uuid) to authenticated, service_role;

comment on function account_unlocked(uuid) is
  'Smie tento účet pracovať? Jediný zdroj pravdy — používa ho RLS na models '
  'INSERT aj web (lib/access.ts). Odomyká plán free_plus/vip alebo rola '
  'admin/superadmin.';

-- ---------------------------------------------------------------------------
-- (c) Zámok — RLS na models INSERT
-- ---------------------------------------------------------------------------
--
-- TOTO je celá hranica. Každá tenant tabuľka (persona, settings, photos,
-- fanvue…) visí cez `model_id` na vlastníctve modelky, takže kto si nezaloží
-- modelku, nemá sa čoho chytiť — ani ručnou URL, ani priamym PostgREST volaním.
-- Jedna brána namiesto dvadsiatich.

drop policy if exists models_owner_insert on models;
create policy models_owner_insert on models
  for insert to authenticated
  with check (
    account_id = (select auth.uid())
    and account_unlocked((select auth.uid()))
  );

-- ---------------------------------------------------------------------------
-- (d) admin_set_plan — ten istý guard, o hodnotu dlhší zoznam
-- ---------------------------------------------------------------------------
--
-- Semantika z 024 sa NEMENÍ: bežné balíky smie prepínať admin, `vip` (oboma
-- smermi) výhradne superadmin. Pribudol len `free_plus` medzi bežné.
--
-- POZOR: `create or replace` prepisuje atribúty, takže pripnutý search_path
-- z 002 sa musí zopakovať (tá istá pasca ako v 013, 016, 021 a 024).

create or replace function admin_set_plan(p_account uuid, p_plan text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_current text;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_plan not in ('free', 'free_plus', 'vip') then
    raise exception 'invalid plan: %', p_plan;
  end if;

  select plan into v_current from accounts where id = p_account for update;
  if v_current is null then raise exception 'account not found'; end if;
  if v_current = p_plan then return v_current; end if;

  if (p_plan = 'vip' or v_current = 'vip') and not is_superadmin() then
    raise exception 'vip plan is superadmin-only' using errcode = '42501';
  end if;

  insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                  amount, note)
  values (p_account, auth.uid(),
          coalesce((select email from accounts where id = p_account), ''),
          coalesce((select email from accounts where id = auth.uid()), ''),
          0, 'plan=' || p_plan || ' was=' || v_current);

  update accounts set plan = p_plan where id = p_account;
  return p_plan;
end;
$$;

revoke execute on function admin_set_plan(uuid, text) from public, anon;
grant execute on function admin_set_plan(uuid, text) to authenticated;

-- ---------------------------------------------------------------------------
-- (e) Sonda — čo unikne, musí byť chyba migrácie
-- ---------------------------------------------------------------------------
--
-- Beží na existujúcom nesuperadmin a NE-VIP účte; všetko, čo zmení, sa na konci
-- zahodí sentinel výnimkou (vnútorný `begin ... exception` je implicitný
-- savepoint). Rovnaký postup ako 021/024.
--
-- Body (2) a (3) sú tu podstatné: bez nich by migrácia prešla aj s dierou
-- v zámku. RLS sa nedá overiť ako vlastník tabuľky (ten ju obchádza), preto sa
-- na ten jediný pokus prepíname cez `set local role authenticated`.

do $$
declare
  v_probe uuid;
  v_role_before text; v_plan_before text;
  v_audit_before bigint;
  v_super uuid;
  v_rec oid;
  v_locked_blocked boolean := false;
  v_unlocked_ok boolean := false;
  v_unlocked_free_plus boolean := false;
  v_unlocked_free boolean := true;
  v_unlocked_vip boolean := false;
  v_unlocked_admin boolean := false;
  v_plus_ok boolean := false;
  v_vip_blocked boolean := false;
  v_dead_blocked boolean := false;
  v_check_blocks boolean := false;
  v_reached boolean := false;
begin
  -- (0) Invariant, na ktorom stojí CELÝ návrh: `record_usage` vetví iba na
  --     'vip'. Vďaka tomu padne `free_plus` do vetvy `else` a účtuje sa presne
  --     ako `free`. Keby niekto pridal vetvu na iný plán, Standard+ by sa začal
  --     účtovať inak než Standard a nikto by si toho nevšimol.
  select p.oid into v_rec from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'record_usage' limit 1;
  if v_rec is null then
    raise exception 'access-gating: record_usage neexistuje';
  end if;
  if pg_get_functiondef(v_rec) not like '%''vip''%' then
    raise exception 'access-gating: record_usage už nevetví na vip — over účtovanie free_plus';
  end if;
  if pg_get_functiondef(v_rec) like '%free_plus%' then
    raise exception 'access-gating: record_usage vetví na free_plus — Standard+ sa účtuje inak než Standard';
  end if;

  select id, role, plan into v_probe, v_role_before, v_plan_before
  from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;
  select id into v_super from accounts where role = 'superadmin' order by created_at limit 1;
  select count(*) into v_audit_before from credit_adjustments;

  if v_probe is null or v_super is null then
    raise notice 'access-gating: sonda preskočená — chýba vhodný nesuperadmin alebo superadmin účet';
  else
    begin
      -- (1) account_unlocked() na všetkých štyroch stavoch
      update accounts set role = 'user', plan = 'free' where id = v_probe;
      v_unlocked_free := account_unlocked(v_probe);

      update accounts set plan = 'free_plus' where id = v_probe;
      v_unlocked_free_plus := account_unlocked(v_probe);

      update accounts set plan = 'vip' where id = v_probe;
      v_unlocked_vip := account_unlocked(v_probe);

      update accounts set plan = 'free', role = 'admin' where id = v_probe;
      v_unlocked_admin := account_unlocked(v_probe);

      -- (2) RLS: zamknutý účet NESMIE založiť modelku
      update accounts set role = 'user', plan = 'free' where id = v_probe;
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe, 'role', 'authenticated')::text, true);
      begin
        execute 'set local role authenticated';
        begin
          insert into models (account_id, name) values (v_probe, 'access-probe-locked');
        exception when others then v_locked_blocked := true;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
      end;

      -- (3) RLS: odomknutý účet cez tú istú cestu PREJDE
      update accounts set plan = 'free_plus' where id = v_probe;
      begin
        execute 'set local role authenticated';
        begin
          insert into models (account_id, name) values (v_probe, 'access-probe-unlocked');
          v_unlocked_ok := true;
        exception when others then v_unlocked_ok := false;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
      end;

      -- (4) admin_set_plan: free_plus je bežný balík, vip ostáva superadmin-only
      update accounts set role = 'admin', plan = 'free' where id = v_probe;
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        v_plus_ok := admin_set_plan(v_probe, 'free_plus') = 'free_plus';
      exception when others then v_plus_ok := false;
      end;
      begin
        perform admin_set_plan(v_probe, 'vip');
      exception when insufficient_privilege then v_vip_blocked := true;
      end;
      begin
        perform admin_set_plan(v_probe, 'pro');
      exception when others then v_dead_blocked := true;
      end;

      -- (5) Constraint musí mŕtvy balík zastaviť aj mimo RPC
      begin
        update accounts set plan = 'pro' where id = v_probe;
      exception when check_violation then v_check_blocks := true;
      end;

      v_reached := true;
      raise exception 'access-gating-sonda-rollback' using errcode = 'P0001';
    exception when raise_exception then
      -- Sem sa dostaneme sentinelom (alebo neočakávaným pádom) — v oboch
      -- prípadoch je sonda odrolovaná. Rozdiel podrží `v_reached`.
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then raise exception 'access-gating: sonda spadla skôr, než dobehla'; end if;
    if v_unlocked_free then raise exception 'access-gating: free účet sa tvári ako odomknutý'; end if;
    if not v_unlocked_free_plus then raise exception 'access-gating: free_plus nie je odomknutý'; end if;
    if not v_unlocked_vip then raise exception 'access-gating: vip nie je odomknutý'; end if;
    if not v_unlocked_admin then raise exception 'access-gating: admin rola neodomyká'; end if;
    if not v_locked_blocked then raise exception 'access-gating: ZAMKNUTÝ ÚČET ZALOŽIL MODELKU — zámok je deravý'; end if;
    if not v_unlocked_ok then raise exception 'access-gating: odomknutý účet nedokázal založiť modelku'; end if;
    if not v_plus_ok then raise exception 'access-gating: admin nedokázal nastaviť free_plus'; end if;
    if not v_vip_blocked then raise exception 'access-gating: admin (nie superadmin) dokázal nastaviť vip'; end if;
    if not v_dead_blocked then raise exception 'access-gating: admin_set_plan pustil mŕtvy balík pro'; end if;
    if not v_check_blocks then raise exception 'access-gating: accounts_plan_check pustil pro'; end if;

    -- Dôkaz upratania: sonda po sebe nesmie nechať nič.
    if exists (
      select 1 from accounts
      where id = v_probe and (role <> v_role_before or plan <> v_plan_before)
    ) then
      raise exception 'access-gating: sonda po sebe nechala zmenený účet %', v_probe;
    end if;
    if (select count(*) from credit_adjustments) <> v_audit_before then
      raise exception 'access-gating: sonda po sebe nechala riadky v credit_adjustments';
    end if;
    if exists (select 1 from models where name like 'access-probe-%') then
      raise exception 'access-gating: sonda po sebe nechala testovacie modelky';
    end if;
  end if;
end $$;

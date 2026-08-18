-- Dva balíky namiesto piatich — `free` a `vip`, nič iné.
--
-- PREČO
-- -----
-- Predplatné končí. Klient si už nekupuje „plán", ale Pipe Coiny (kredit) a
-- míňa ich tak, ako modelka pracuje. Zostávajú preto len dve možnosti, ktoré
-- Marek v admine naozaj prideľuje:
--
--   free — bežný účet, účtuje sa `pricing.multiplier` (2.0), na tom zarábame
--   vip  — kamaráti, účtuje sa nákupná cena Atlasu (1.0), nezarábame nič
--
-- `starter`, `pro` a `custom` nikdy nič neriadili: jediné miesto, kde plán
-- ovplyvňuje peniaze, je `case when v_plan = 'vip'` v `record_usage` (021).
-- Boli to nálepky v admin tabuľke. Preto sa dajú zlúčiť do `free` bez toho,
-- aby sa komukoľvek zmenil zostatok alebo cena — mení sa len text v stĺpci.
--
-- ČO SA TU ZÁMERNE NEMENÍ
-- -----------------------
-- * `record_usage` — VIP pravidlo ostáva presne také, aké ho nastavilo 021.
-- * `credit_balance_usd`, `usage_events` — jednotka ostáva dolár. Pipe Coin je
--   prezentačná vrstva webu (`web/lib/coins.ts`), nie typ v databáze.
-- * `admin_list_accounts` — vracia `a.plan` ako text bez whitelistu, takže sa
--   jej zúženie zoznamu netýka. Sonda nižšie to overuje.

-- ---------------------------------------------------------------------------
-- (a) Mŕtve balíky → free
-- ---------------------------------------------------------------------------
--
-- Musí ísť PRED výmenou constraintu, inak by nový check padol na existujúcich
-- riadkoch. Počet sa vypíše do výstupu migrácie — čakáme jednotky.

do $$
declare v_moved int;
begin
  update accounts set plan = 'free' where plan in ('starter', 'pro', 'custom');
  get diagnostics v_moved = row_count;
  raise notice '024: % účtov presunutých z mŕtvych balíkov na free', v_moved;
end $$;

-- ---------------------------------------------------------------------------
-- (b) accounts.plan — whitelist v schéme
-- ---------------------------------------------------------------------------
--
-- 021 pridalo `accounts_plan_check` s piatimi hodnotami. Meno constraintu
-- ostáva rovnaké, aby sa v `pg_constraint` nehromadili historické verzie.

alter table accounts drop constraint if exists accounts_plan_check;
alter table accounts
  add constraint accounts_plan_check
  check (plan in ('free', 'vip'));

-- ---------------------------------------------------------------------------
-- (c) admin_set_plan — ten istý zoznam, tie isté práva
-- ---------------------------------------------------------------------------
--
-- Semantika sa NEMENÍ, len ubudli hodnoty: admin smie prepínať bežné balíky,
-- `vip` (oboma smermi) smie výhradne superadmin. Audit ide ďalej do
-- `credit_adjustments` s amount 0.
--
-- POZOR: `create or replace` prepisuje aj atribúty funkcie, takže pripnutý
-- search_path z 002 sa musí zopakovať (tá istá pasca ako v 013, 016 a 021).

create or replace function admin_set_plan(p_account uuid, p_plan text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_current text;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_plan not in ('free', 'vip') then
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
-- (d) Poistky — čo unikne, musí byť chyba migrácie
-- ---------------------------------------------------------------------------
--
-- Sonda beží na existujúcom nesuperadmin a NE-VIP účte a všetko, čo zmení
-- (rola, plán, audit riadky), sa na konci zahodí: vnútorný `begin ... exception`
-- je implicitný savepoint, takže sentinel výnimka vráti stav späť. Rovnaký
-- postup ako v 021 — netreba zakladať testovací účet (a ani sa nedá lacno:
-- `accounts.id` má FK na `auth.users`).

do $$
declare
  v_probe uuid;
  v_role_before text; v_plan_before text; v_balance_before numeric;
  v_audit_before bigint;
  v_super uuid;
  v_vip_blocked boolean := false;
  v_dead_blocked boolean := false;
  v_unvip_blocked boolean := false;
  v_free_ok boolean := false;
  v_super_vip_ok boolean := false;
  v_super_free_ok boolean := false;
  v_check_blocks boolean := false;
  v_list_ok boolean := false;
  v_reached boolean := false;
begin
  -- (1) Po (a) nesmie v tabuľke ostať ani jeden mŕtvy balík.
  if exists (select 1 from accounts where plan not in ('free', 'vip')) then
    raise exception '024: v accounts ostal balík mimo (free, vip)';
  end if;

  -- (2) Schéma a RPC musia mať ten istý zoznam — inak by buď `admin_set_plan`
  --     padal na constrainte, alebo by cez constraint prešlo, čo RPC zakazuje.
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.accounts'::regclass and conname = 'accounts_plan_check'
      and pg_get_constraintdef(oid) like '%vip%'
      and pg_get_constraintdef(oid) not like '%starter%'
      and pg_get_constraintdef(oid) not like '%custom%'
  ) then
    raise exception '024: accounts_plan_check nesedí na (free, vip)';
  end if;

  -- (3) Marža ostáva pred klientom skrytá (kontrola z 021 sa opakuje, lebo
  --     odteraz sa spotreba klientovi zobrazuje v coinoch a je to jediný
  --     stĺpec, ktorý sa doňho previesť NESMIE).
  if has_column_privilege('authenticated', 'public.usage_events', 'atlas_cost_usd', 'SELECT')
     or has_column_privilege('anon', 'public.usage_events', 'atlas_cost_usd', 'SELECT') then
    raise exception '024: usage_events.atlas_cost_usd je pre klienta čitateľný — marža unikla';
  end if;

  -- (4) Živá skúška guardu.
  select id, role, plan, credit_balance_usd
    into v_probe, v_role_before, v_plan_before, v_balance_before
  from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;
  select id into v_super from accounts where role = 'superadmin' order by created_at limit 1;
  select count(*) into v_audit_before from credit_adjustments;

  if v_probe is null or v_super is null then
    raise notice '024: sonda preskočená — chýba vhodný nesuperadmin alebo superadmin účet';
  else
    begin
      update accounts set role = 'admin', plan = 'free' where id = v_probe;

      -- Obyčajný admin.
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        perform admin_set_plan(v_probe, 'vip');
      exception when insufficient_privilege then v_vip_blocked := true;
      end;
      begin
        -- Mŕtvy balík musí RPC odmietnuť, nie ho ticho pustiť na constraint.
        perform admin_set_plan(v_probe, 'pro');
      exception when others then v_dead_blocked := true;
      end;

      -- Superadmin: vip smie dať aj vziať.
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_super)::text, true);
      begin
        v_super_vip_ok := admin_set_plan(v_probe, 'vip') = 'vip';
      exception when others then v_super_vip_ok := false;
      end;

      -- A z VIP účtu nesmie obyčajný admin spraviť free (inak by kamarátovi
      -- zdvojnásobil cenu bežný admin).
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        perform admin_set_plan(v_probe, 'free');
      exception when insufficient_privilege then v_unvip_blocked := true;
      end;

      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_super)::text, true);
      begin
        v_super_free_ok := admin_set_plan(v_probe, 'free') = 'free';
      exception when others then v_super_free_ok := false;
      end;

      -- Bežný balík ostáva adminovi. Zmena musí byť reálna, preto najprv vip
      -- (superadminom) a späť na free adminom by neprešlo — testujeme teda
      -- opačný, dovolený smer: free → free vracia skratkou, takže overíme
      -- aspoň to, že RPC adminovi nespadne na právach.
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        v_free_ok := admin_set_plan(v_probe, 'free') = 'free';
      exception when others then v_free_ok := false;
      end;

      -- Constraint musí mŕtvy balík zastaviť aj mimo RPC.
      begin
        update accounts set plan = 'pro' where id = v_probe;
      exception when check_violation then v_check_blocks := true;
      end;

      -- `admin_list_accounts` sa nemenila a musí ďalej chodiť.
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_super)::text, true);
      begin
        v_list_ok := (select count(*) from admin_list_accounts()) > 0;
      exception when others then v_list_ok := false;
      end;

      v_reached := true;
      raise exception 'plans-sonda-rollback' using errcode = 'P0001';
    exception when raise_exception then
      -- Sem sa dostaneme sentinelom (alebo neočakávaným pádom) — v oboch
      -- prípadoch je sonda odrolovaná. Rozdiel podrží `v_reached`.
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then raise exception '024: sonda spadla skôr, než dobehla'; end if;
    if not v_vip_blocked then raise exception '024: admin (nie superadmin) dokázal nastaviť vip'; end if;
    if not v_dead_blocked then raise exception '024: admin_set_plan pustil mŕtvy balík pro'; end if;
    if not v_super_vip_ok then raise exception '024: superadmin nedokázal nastaviť vip'; end if;
    if not v_unvip_blocked then raise exception '024: admin dokázal zobrať vip'; end if;
    if not v_super_free_ok then raise exception '024: superadmin nedokázal zobrať vip'; end if;
    if not v_free_ok then raise exception '024: admin stratil právo na bežný balík'; end if;
    if not v_check_blocks then raise exception '024: accounts_plan_check pustil pro'; end if;
    if not v_list_ok then raise exception '024: admin_list_accounts prestala fungovať'; end if;

    -- (5) Dôkaz upratania: sonda po sebe nesmie nechať ani zmenený riadok,
    --     ani audit záznam v `credit_adjustments`.
    if exists (
      select 1 from accounts
      where id = v_probe
        and (role <> v_role_before or plan <> v_plan_before
             or credit_balance_usd <> v_balance_before)
    ) then
      raise exception '024: sonda po sebe nechala zmenený účet %', v_probe;
    end if;
    if (select count(*) from credit_adjustments) <> v_audit_before then
      raise exception '024: sonda po sebe nechala riadky v credit_adjustments';
    end if;
  end if;
end $$;

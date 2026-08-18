-- Balík VIP — kamaráti platia presne toľko, koľko nás stoja.
--
-- PREČO
-- -----
-- Marek chce zopár ľuďom dať účet, ktorý sa účtuje v nákupnej cene Atlasu:
-- žiadna marža, ale kredit sa naďalej míňa a spotreba sa naďalej meria. To je
-- niečo iné než `unlimited` (013) — ten odpočet PRESKAKUJE. VIP odpočítava,
-- len iným násobkom (1.0 namiesto štandardných 2.0 z `pricing.multiplier`).
-- Na webe sa balík nikde neponúka; prideliť ho vie výhradne superadmin.
--
-- PREČO TO POČÍTA DATABÁZA A NIE VOLAJÚCI
-- ---------------------------------------
-- Účtovanú sumu dnes počíta volajúci a posiela ju do `record_usage` hotovú —
-- a robia to DVE nezávislé implementácie tej istej rovnice: `MeteredLlm._bill_inner`
-- (`worker/src/credits.py`) a `computeCost` (`web/lib/pricing.ts`). Keby VIP
-- znamenal „obe strany si nezabudnú pozrieť plán účtu", stačí jedna cesta, kde
-- sa to zabudne (napr. prepis textu vo wizarde), a kamarát zaplatí dvojnásobok.
-- Preto je zľava ZÁMERNE vynútená tu: `record_usage` si účtovanú sumu pri VIP
-- účte prepočíta sám na `p_atlas_cost_usd` a hodnotu od volajúceho ignoruje.
-- Worker ani web sa preto meniť nemusia a ani sa NESMÚ „opraviť" tak, že si
-- multiplier začnú vyberať podľa plánu — jediná autorita je táto funkcia.
--
-- Do `usage_events` ide `atlas_cost_usd` vždy nezmenený (naša reálna nákupka),
-- takže admin prehľady sedia ďalej — marža VIP riadku je presne 0, nie záporná.

-- ---------------------------------------------------------------------------
-- (a) accounts.plan — whitelist konečne aj v schéme
-- ---------------------------------------------------------------------------
--
-- 009 pridalo `plan` bez `check` a zoznam povolených hodnôt žil len vo vnútri
-- `admin_set_plan`. Odteraz je `vip` účtovacie pravidlo, nie kozmetika, takže
-- preklep ('Vip', 'vip ') by tichým minutím `case` vrátil klienta na plnú cenu.
-- Constraint drží obe strany v jednom zozname.
alter table accounts
  add constraint accounts_plan_check
  check (plan in ('free', 'starter', 'pro', 'custom', 'vip'));

-- ---------------------------------------------------------------------------
-- (b) record_usage — účtovaná suma sa pri VIP prepočíta v DB
-- ---------------------------------------------------------------------------
--
-- POZOR: `create or replace` prepisuje aj atribúty funkcie, takže pripnutý
-- search_path z 002 sa musí zopakovať (rovnaká pasca ako v 013 a 016). Grants
-- ostávajú (service_role), signatúra sa nemení.

create or replace function record_usage(
  p_model uuid, p_kind text,
  p_input_tokens int, p_output_tokens int, p_unit_count int,
  p_atlas_cost_usd numeric, p_charged_usd numeric
) returns numeric language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid; v_name text; v_email text;
  v_plan text; v_unlimited boolean; v_balance numeric; v_charged numeric;
begin
  select m.account_id, coalesce(m.name, '') into v_account, v_name
  from models m where m.id = p_model;
  select coalesce(a.email, ''), a.plan, a.unlimited
    into v_email, v_plan, v_unlimited
  from accounts a where a.id = v_account;

  -- Jediné miesto, kde sa o VIP rozhoduje. `round(...,6)` je ten istý počet
  -- desatinných miest, aký zapisuje worker (`round(atlas, 6)`), nech sa dajú
  -- riadky ledgeru porovnávať.
  v_charged := case
    when v_plan = 'vip' then round(coalesce(p_atlas_cost_usd, 0), 6)
    else p_charged_usd
  end;

  -- Ledger prvý a bez podmienky — spotreba neobmedzeného účtu je stále náklad
  -- a musí byť v admin prehľadoch vidieť. `atlas_cost_usd` ide vždy taký, aký
  -- prišiel: je to naša nákupka a počíta sa z neho marža.
  insert into usage_events (model_id, account_id, account_email, model_name,
    kind, input_tokens, output_tokens, unit_count, atlas_cost_usd, charged_usd)
  values (p_model, v_account, coalesce(v_email, ''), coalesce(v_name, ''),
    p_kind, p_input_tokens, p_output_tokens,
    p_unit_count, p_atlas_cost_usd, v_charged);

  select a.credit_balance_usd into v_balance from accounts a where a.id = v_account;

  -- `unlimited` sa skladá NAD vip: neobmedzenému účtu sa neodpočíta nič, aj
  -- keby mal plán vip (a v ledgeri ostane aj tak nákupná cena).
  if not coalesce(v_unlimited, false) then
    update accounts set credit_balance_usd = credit_balance_usd - v_charged
    where id = v_account
    returning credit_balance_usd into v_balance;
  end if;

  -- Vždy aktuálny zostatok (pri unlimited nezmenený) — volajúci si ho loguje.
  return v_balance;
end;
$$;

-- ---------------------------------------------------------------------------
-- (c) admin_set_plan — vip smie prideliť (a odobrať) len superadmin
-- ---------------------------------------------------------------------------
--
-- Ostatné balíky ostávajú adminovi. VIP je peňazovod (klient prestane nosiť
-- maržu), preto rovnaká váha ako `admin_set_role` / `admin_set_unlimited`:
-- `is_superadmin()`. Guard platí OBOMA smermi — kto nesmie VIP dať, nesmie ho
-- ani potichu zobrať, inak by kamarátovi zdvojnásobil cenu bežný admin.
--
-- Audit ide do `credit_adjustments` (amount 0 — balíkom sa peniazmi nehýbe,
-- ale kto komu čo kedy nastavil musí byť dohľadateľné, rovnako ako pri
-- `admin_set_unlimited`). Zapisujú sa aj odtlačky e-mailov (016).

create or replace function admin_set_plan(p_account uuid, p_plan text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_current text;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_plan not in ('free', 'starter', 'pro', 'custom', 'vip') then
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

-- `create or replace` grants nemení (funkcia sa nedropuje), ale nech je audit
-- čitateľný na jednom mieste — rovnaký režim ako v 009.
revoke execute on function admin_set_plan(uuid, text) from public, anon;
grant execute on function admin_set_plan(uuid, text) to authenticated;

-- `admin_list_accounts` (013) vracia `a.plan` ako text bez whitelistu, takže
-- `vip` cez ňu prejde bez zmeny — admin tabuľka ho uvidí. Zámerne sa nemení.

-- ---------------------------------------------------------------------------
-- (d) Poistky — čo unikne, musí byť chyba migrácie
-- ---------------------------------------------------------------------------

do $$
declare
  v_probe uuid;
  v_role_before text; v_plan_before text;
  v_super uuid;
  v_vip_blocked boolean := false;
  v_normal_ok boolean := false;
  v_super_ok boolean := false;
  v_reached boolean := false;
begin
  -- (1) Marža ostáva pred klientom skrytá aj po prepise `record_usage`.
  if has_column_privilege('authenticated', 'public.usage_events', 'atlas_cost_usd', 'SELECT')
     or has_column_privilege('anon', 'public.usage_events', 'atlas_cost_usd', 'SELECT') then
    raise exception 'usage_events.atlas_cost_usd je pre klienta čitateľný — marža unikla';
  end if;

  -- (2) Schéma a RPC musia mať ten istý zoznam — inak by `vip` z admin RPC
  --     spadol na constrainte (alebo naopak prešiel preklep).
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.accounts'::regclass and conname = 'accounts_plan_check'
      and pg_get_constraintdef(oid) like '%vip%'
  ) then
    raise exception 'accounts_plan_check nepozná vip';
  end if;

  -- (3) Živá skúška guardu. Beží na existujúcom nesuperadmin účte a VŠETKO,
  --     čo v sonde zmení (rola, plán, audit riadok), sa na konci zahodí —
  --     vnútorný `begin ... exception` je implicitný savepoint, takže sentinel
  --     výnimka vráti stav späť. Preto tu netreba zakladať testovací účet.
  select id, role, plan into v_probe, v_role_before, v_plan_before
  from accounts where role <> 'superadmin' order by created_at limit 1;
  select id into v_super from accounts where role = 'superadmin' order by created_at limit 1;

  if v_probe is null or v_super is null then
    raise notice 'VIP guard sonda preskočená — chýba nesuperadmin alebo superadmin účet';
  else
    begin
      update accounts set role = 'admin' where id = v_probe;

      -- Obyčajný admin: vip nesmie, bežný balík smie.
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        perform admin_set_plan(v_probe, 'vip');
      exception when insufficient_privilege then v_vip_blocked := true;
      end;
      begin
        v_normal_ok := admin_set_plan(v_probe, 'pro') = 'pro';
      exception when others then v_normal_ok := false;
      end;

      -- Superadmin: vip smie.
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_super)::text, true);
      begin
        v_super_ok := admin_set_plan(v_probe, 'vip') = 'vip';
      exception when others then v_super_ok := false;
      end;

      v_reached := true;
      raise exception 'vip-sonda-rollback' using errcode = 'P0001';
    exception when raise_exception then
      -- Sem sa dostaneme sentinelom (alebo neočakávaným pádom) — v oboch
      -- prípadoch je sonda odrolovaná. Rozdiel podrží `v_reached`.
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then
      raise exception 'VIP guard sonda spadla skôr, než dobehla';
    end if;
    if not v_vip_blocked then
      raise exception 'admin (nie superadmin) dokázal nastaviť vip';
    end if;
    if not v_normal_ok then
      raise exception 'admin stratil právo meniť bežné balíky';
    end if;
    if not v_super_ok then
      raise exception 'superadmin nedokázal nastaviť vip';
    end if;
    if exists (
      select 1 from accounts
      where id = v_probe and (role <> v_role_before or plan <> v_plan_before)
    ) then
      raise exception 'sonda po sebe nechala zmenený účet %', v_probe;
    end if;
  end if;
end $$;

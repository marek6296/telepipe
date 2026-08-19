-- Sloty na modelky + uvítací kredit pri odomknutí.
--
-- PREČO
-- -----
-- Každá modelka je bežiaca Telegram session a drží miesto na replike
-- (`MAX_TENANTS=25`). Bez stropu si jeden účet spraví pätnásť testovacích
-- modeliek a zožerie kapacitu zadarmo. Slot je poistka aj záväzok — nie
-- primárny zdroj príjmu.
--
-- PRAVIDLO
-- --------
-- Slot je KAPACITA, nie vlastníctvo konkrétnej modelky:
--
--     počet modeliek účtu  <=  accounts.model_slots
--
-- Vďaka tomu zmazanie modelky miesto automaticky uvoľní a klient si môže
-- spraviť novú — bez akéhokoľvek vracania či prepisovania slotov. Mazanie je
-- v `models` tvrdé (`delete`, žiadny `deleted_at`), takže `count(*)` je pravda.
--
-- Pauznutá modelka slot DRŽÍ. Stále má session aj miesto na replike.
--
-- KTO SLOTY NEPOTREBUJE
-- ---------------------
-- `role in ('admin','superadmin')` alebo `plan = 'vip'` — neobmedzene. Marek
-- prejde rolou, kamarát plánom; ani jedného sa táto zmena nedotkne.
--
-- CENY
-- ----
-- * prvý slot   — zadarmo, pripíše sa pri odomknutí na `free_plus`
-- * ďalší slot  — $20 (v coinoch, `coinPriceFromUsdCost` netreba, je to rovná suma)
-- * strop       — 8 slotov na účet
-- * uvítací kredit — $5 pri PRVOM odomknutí, raz za život účtu
--
-- ÚČTOVANIA SA TO NEDOTÝKA
-- ------------------------
-- `record_usage` (021) sa vetví iba na `'vip'`. Sloty ani uvítací kredit do
-- nej nesiahajú — menia len `credit_balance_usd` a nový stĺpec.

-- ---------------------------------------------------------------------------
-- (a) Stĺpce
-- ---------------------------------------------------------------------------

alter table accounts
  add column if not exists model_slots int not null default 0,
  add column if not exists welcome_grant_at timestamptz;

comment on column accounts.model_slots is
  'Koľko modeliek smie účet mať naraz. Prvý slot dá odomknutie, ďalšie sa kupujú.';
comment on column accounts.welcome_grant_at is
  'Kedy účet dostal jednorazový uvítací kredit. NULL = ešte nedostal.';

-- Klient musí svoj strop vidieť (koľko slotov mám / koľko modeliek).
grant select (model_slots) on accounts to authenticated;

-- ---------------------------------------------------------------------------
-- (b) Kto je zo slotov vyňatý
-- ---------------------------------------------------------------------------

create or replace function account_slot_exempt(p_account uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
  select exists (
    select 1 from accounts
    where id = p_account
      and (role in ('admin', 'superadmin') or plan = 'vip')
  );
$$;

revoke execute on function account_slot_exempt(uuid) from public, anon;
grant execute on function account_slot_exempt(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- (c) Strop sa stráži v DB, nie v UI
-- ---------------------------------------------------------------------------
--
-- Trigger, nie kontrola v server action: modelka sa dá založiť viacerými
-- cestami a dva súbežné requesty pri jednom voľnom slote by kontrolu v appke
-- oba prešli. `for update` na účte serializuje aj ten súbeh.

create or replace function models_enforce_slot_limit()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_slots int;
  v_used  int;
begin
  if account_slot_exempt(new.account_id) then
    return new;
  end if;

  select model_slots into v_slots
    from accounts where id = new.account_id for update;

  if v_slots is null then
    raise exception 'account not found' using errcode = '23503';
  end if;

  select count(*) into v_used from models where account_id = new.account_id;

  if v_used >= v_slots then
    raise exception 'no free model slot (% used, % owned)', v_used, v_slots
      using errcode = '23514', hint = 'buy_model_slot';
  end if;

  return new;
end;
$$;

drop trigger if exists models_slot_limit on models;
create trigger models_slot_limit
  before insert on models
  for each row execute function models_enforce_slot_limit();

-- ---------------------------------------------------------------------------
-- (d) Nákup slotu
-- ---------------------------------------------------------------------------

create table if not exists model_slot_purchases (
  id bigint generated always as identity primary key,
  account_id uuid not null references accounts(id) on delete cascade,
  price_usd numeric not null,
  slots_after int not null,
  created_at timestamptz not null default now()
);
create index if not exists model_slot_purchases_account_idx
  on model_slot_purchases (account_id, created_at desc);

alter table model_slot_purchases enable row level security;
revoke all on model_slot_purchases from anon, authenticated;

create or replace function buy_model_slot()
returns table (slots int, balance_usd numeric)
language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid := auth.uid();
  v_price   numeric := 20;
  v_max     int := 8;
  v_slots   int;
  v_balance numeric;
begin
  if v_account is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;

  -- Zamknutý účet (ešte neschválený) si slot kúpiť nemôže.
  if not account_unlocked(v_account) then
    raise exception 'account locked' using errcode = '42501';
  end if;

  -- Vyňatí sloty nepotrebujú — nech si ich omylom nekupujú.
  if account_slot_exempt(v_account) then
    raise exception 'account does not need slots' using errcode = '23514';
  end if;

  select model_slots, credit_balance_usd
    into v_slots, v_balance
    from accounts where id = v_account for update;

  if v_slots is null then
    raise exception 'account not found' using errcode = '23503';
  end if;

  if v_slots >= v_max then
    raise exception 'slot limit reached (max %)', v_max using errcode = '23514';
  end if;

  if v_balance < v_price then
    raise exception 'insufficient credits' using errcode = '23514';
  end if;

  update accounts
     set credit_balance_usd = credit_balance_usd - v_price,
         model_slots        = model_slots + 1
   where id = v_account
   returning model_slots, credit_balance_usd into v_slots, v_balance;

  insert into model_slot_purchases (account_id, price_usd, slots_after)
  values (v_account, v_price, v_slots);

  return query select v_slots, v_balance;
end;
$$;

revoke execute on function buy_model_slot() from public, anon;
grant execute on function buy_model_slot() to authenticated;

-- ---------------------------------------------------------------------------
-- (e) Odomknutie = prvý slot + uvítací kredit
-- ---------------------------------------------------------------------------
--
-- Rozširuje `admin_set_plan` z access-gating migrácie. Zachováva jej správanie
-- do bodky (práva, VIP pravidlo, audit riadok) a dopĺňa jediné: pri PRVOM
-- prechode na odomknutý plán pripíše $5 a jeden slot.
--
-- Idempotencia je na `welcome_grant_at`, nie na pláne — prepnutie tam a späť
-- teda druhý kredit NEDÁ.

create or replace function admin_set_plan(p_account uuid, p_plan text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_current text;
  v_granted timestamptz;
  v_welcome numeric := 5;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_plan not in ('free', 'free_plus', 'vip') then
    raise exception 'invalid plan: %', p_plan;
  end if;

  select plan, welcome_grant_at into v_current, v_granted
    from accounts where id = p_account for update;
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

  -- Prvé odomknutie: rozbehový kredit + slot na prvú modelku.
  if p_plan in ('free_plus', 'vip') and v_granted is null then
    update accounts
       set credit_balance_usd = credit_balance_usd + v_welcome,
           model_slots        = greatest(model_slots, 1),
           welcome_grant_at   = now()
     where id = p_account;

    insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                    amount, note)
    values (p_account, auth.uid(),
            coalesce((select email from accounts where id = p_account), ''),
            coalesce((select email from accounts where id = auth.uid()), ''),
            v_welcome, 'welcome grant + 1 model slot');
  end if;

  return p_plan;
end;
$$;

revoke execute on function admin_set_plan(uuid, text) from public, anon;
grant execute on function admin_set_plan(uuid, text) to authenticated;

-- ---------------------------------------------------------------------------
-- (f) Dorovnanie existujúcich účtov
-- ---------------------------------------------------------------------------
--
-- Kto už odomknutý JE, dostal to ešte pred existenciou slotov. Bez tohto by
-- mal nula slotov a nevedel by si založiť ani prvú modelku — teda presne to,
-- na čo mu prístup schválili. Vyňatých (admin/superadmin/vip) sa to netýka,
-- tí strop nemajú.

update accounts
   set model_slots      = greatest(model_slots, 1),
       credit_balance_usd = credit_balance_usd
         + case when welcome_grant_at is null then 5 else 0 end,
       welcome_grant_at = coalesce(welcome_grant_at, now())
 where plan = 'free_plus';

-- Kto už modelky má z čias pred slotmi, nech o ne nepríde ani sa nezasekne:
-- slotov dostane aspoň toľko, koľko má modeliek.
update accounts a
   set model_slots = greatest(a.model_slots,
                              (select count(*) from models m where m.account_id = a.id))
 where not account_slot_exempt(a.id);

-- ---------------------------------------------------------------------------
-- (g) Sonda
-- ---------------------------------------------------------------------------

do $$
declare
  v_missing text;
  v_bad int;
begin
  select string_agg(c, ', ') into v_missing from (
    select c from unnest(array['model_slots', 'welcome_grant_at']) c
    where not exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = 'accounts' and column_name = c
    )
  ) t;
  if v_missing is not null then
    raise exception 'chýbajú stĺpce na accounts: %', v_missing;
  end if;

  if not exists (select 1 from pg_trigger where tgname = 'models_slot_limit') then
    raise exception 'trigger models_slot_limit nevznikol';
  end if;

  -- Nikto nesmie zostať s menej slotmi, než má modeliek.
  select count(*) into v_bad
    from accounts a
   where not account_slot_exempt(a.id)
     and (select count(*) from models m where m.account_id = a.id) > a.model_slots;
  if v_bad > 0 then
    raise exception 'po dorovnaní má % účtov viac modeliek než slotov', v_bad;
  end if;

  raise notice 'model slots OK';
end $$;

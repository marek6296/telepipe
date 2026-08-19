-- Managed hlasy, účtovanie za kus (hlasovka/fotka) a plán `vip_lite`.
--
-- TRI VECI NARAZ, LEBO SA DOTÝKAJÚ TÝCH ISTÝCH MIEST
-- --------------------------------------------------
-- `record_usage` sa mení kvôli `vip_lite` a zároveň ňou pôjde aj účtovanie za
-- kus. Rozdeliť to do dvoch migrácií by znamenalo prepísať tú istú funkciu
-- dvakrát za sebou.

-- ---------------------------------------------------------------------------
-- (a) vip_lite — plán medzi `free_plus` a `vip`
-- ---------------------------------------------------------------------------

alter table accounts drop constraint if exists accounts_plan_check;
alter table accounts
  add constraint accounts_plan_check
  check (plan in ('free', 'free_plus', 'vip_lite', 'vip'));

-- ---------------------------------------------------------------------------
-- (b) app_config — JEDNA tabuľka na všetky ceny a stropy
-- ---------------------------------------------------------------------------
--
-- PREČO TABUĽKA A NIE KONŠTANTY
-- Cena musí byť na dvoch miestach naraz: transakcia ju strháva, ale UI ju
-- musí napísať skôr, než klient klikne. Keď je v kóde, sú to dve pravdy a raz
-- sa rozídu — tlačidlo sľúbi jedno a účet strhne druhé. Keď je v tabuľke,
-- pravda je jedna a mení sa jedným UPDATE bez deployu.
--
-- `value`     — čo zaplatí bežný (Standard+) klient
-- `our_cost`  — čo to reálne stojí nás; z neho sa počíta cena pre `vip` (1:1)
--               a `vip_lite` (1.5×), rovnako ako pri tokenoch
--
-- Pri hlasovke cez KLIENTOV ElevenLabs kľúč je náš náklad nula — platí ju on
-- priamo ElevenLabs. Pri managed hlase (náš kľúč) platíme TTS aj ambient.

create table if not exists app_config (
  key      text primary key,
  value    numeric not null check (value >= 0),
  our_cost numeric not null default 0 check (our_cost >= 0),
  note     text not null default '',
  updated_at timestamptz not null default now()
);

insert into app_config (key, value, our_cost, note) values
  ('voice_managed_usd', 0.50, 0.14, 'Hlasovka nasim hlasom (nas kluc) - TTS + ambient plati me my'),
  ('voice_own_usd',     0.30, 0,    'Hlasovka klientovym klucom - ElevenLabs plati on'),
  ('photo_usd',         0.10, 0,    'Odoslana fotka'),
  ('model_slot_usd',   20.00, 0,    'Dalsi slot na modelku'),
  ('max_model_slots',   8,    0,    'Strop slotov na ucet')
on conflict (key) do nothing;

alter table app_config enable row level security;
revoke all on app_config from anon, authenticated;
-- Klient ceny vidieť musí (píšu sa mu pri zapnutí hlasoviek aj pri kúpe slotu).
-- `our_cost` je naša nákupka — tú nevidí nikto okrem admina.
grant select (key, value, note) on app_config to authenticated;
drop policy if exists app_config_read on app_config;
create policy app_config_read on app_config for select to authenticated using (true);

-- Jedna hodnota z konfigurácie; `p_default` keď kľúč chýba.
create or replace function config_value(p_key text, p_default numeric default 0)
returns numeric language sql stable security definer
set search_path = public, pg_temp as $fn$
  select coalesce((select value from app_config where key = p_key), p_default);
$fn$;

revoke execute on function config_value(text, numeric) from public, anon;
grant execute on function config_value(text, numeric) to authenticated, service_role;

-- Cena slotu a strop sa už nečítajú z kódu, ale odtiaľto.
create or replace function buy_model_slot()
returns table (slots int, balance_usd numeric)
language plpgsql security definer
set search_path = public, pg_temp as $fn$
declare
  v_account uuid := auth.uid();
  v_price   numeric := config_value('model_slot_usd', 20);
  v_max     int     := config_value('max_model_slots', 8)::int;
  v_slots   int;
  v_balance numeric;
begin
  if v_account is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  if not account_unlocked(v_account) then
    raise exception 'account locked' using errcode = '42501';
  end if;
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
$fn$;

revoke execute on function buy_model_slot() from public, anon;
grant execute on function buy_model_slot() to authenticated;

-- ---------------------------------------------------------------------------
-- (c) usage_events.kind — pribúda `photo`
-- ---------------------------------------------------------------------------
--
-- `voice` tam je od 001, len ho doteraz nikto nezapisoval.

alter table usage_events drop constraint if exists usage_events_kind_check;
alter table usage_events add constraint usage_events_kind_check check (
  kind in ('chat', 'assist', 'builder', 'summary', 'vision', 'audio', 'voice', 'photo')
);

-- ---------------------------------------------------------------------------
-- (d) record_usage — pribúda vetva `vip_lite`
-- ---------------------------------------------------------------------------
--
-- Zvyšok funkcie je ZNAK PO ZNAKU pôvodný. Mení sa jediný `case`.
--
-- Prečo cez tú istú funkciu ide aj účtovanie za kus: hlasovka aj fotka majú
-- „našu nákupku" (`atlas_cost_usd`) a „cenu pre klienta" (`charged_usd`)
-- presne ako token. Vďaka tomu platia zľavy plánov automaticky a ledger má
-- jeden tvar — netreba druhú účtovnú cestu, ktorá by časom začala klamať.

create or replace function record_usage(
  p_model uuid, p_kind text, p_input_tokens integer, p_output_tokens integer,
  p_unit_count integer, p_atlas_cost_usd numeric, p_charged_usd numeric
) returns numeric language plpgsql security definer
set search_path = public, pg_temp as $fn$
declare
  v_account uuid; v_name text; v_email text;
  v_plan text; v_unlimited boolean; v_balance numeric; v_charged numeric;
begin
  select m.account_id, coalesce(m.name, '') into v_account, v_name
  from models m where m.id = p_model;
  select coalesce(a.email, ''), a.plan, a.unlimited
    into v_email, v_plan, v_unlimited
  from accounts a where a.id = v_account;

  -- Jediné miesto, kde sa o marži rozhoduje.
  --   vip      — 1:1 nákupka, nulová marža (kamaráti)
  --   vip_lite — 1.5× nákupka, pokryje náklad a nechá tretinu nám
  --   ostatní  — `p_charged_usd`, teda `pricing.multiplier` (2.0) z workera
  v_charged := case
    when v_plan = 'vip'      then round(coalesce(p_atlas_cost_usd, 0), 6)
    when v_plan = 'vip_lite' then round(coalesce(p_atlas_cost_usd, 0) * 1.5, 6)
    else p_charged_usd
  end;

  insert into usage_events (model_id, account_id, account_email, model_name,
    kind, input_tokens, output_tokens, unit_count, atlas_cost_usd, charged_usd)
  values (p_model, v_account, coalesce(v_email, ''), coalesce(v_name, ''),
    p_kind, p_input_tokens, p_output_tokens,
    p_unit_count, p_atlas_cost_usd, v_charged);

  select a.credit_balance_usd into v_balance from accounts a where a.id = v_account;

  if not coalesce(v_unlimited, false) then
    update accounts set credit_balance_usd = credit_balance_usd - v_charged
    where id = v_account
    returning credit_balance_usd into v_balance;
  end if;

  return v_balance;
end;
$fn$;

-- ---------------------------------------------------------------------------
-- (e) admin_set_plan — vip_lite do whitelistu
-- ---------------------------------------------------------------------------
--
-- `vip_lite` smie prideliť aj admin (nielen superadmin) — nie je to nulová
-- marža, len nižšia. Uvítací kredit a prvý slot platia rovnako ako pri
-- `free_plus`, lebo aj `vip_lite` je odomknutý účet.

create or replace function admin_set_plan(p_account uuid, p_plan text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $fn$
declare
  v_current text;
  v_granted timestamptz;
  v_welcome numeric := 5;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_plan not in ('free', 'free_plus', 'vip_lite', 'vip') then
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

  if p_plan in ('free_plus', 'vip_lite', 'vip') and v_granted is null then
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
$fn$;

revoke execute on function admin_set_plan(uuid, text) from public, anon;
grant execute on function admin_set_plan(uuid, text) to authenticated;

-- `vip_lite` má sloty ako Standard+ (zľava je na spotrebe, nie na kapacite),
-- takže `account_slot_exempt` sa zámerne NEMENÍ — vyňatý ostáva len `vip`.

-- ---------------------------------------------------------------------------
-- (f) Managed hlasy
-- ---------------------------------------------------------------------------
--
-- Hlasy z NÁŠHO ElevenLabs účtu, ktoré si klient môže vybrať namiesto
-- pripájania vlastného kľúča. V tabuľke, nie v kóde: Marek ich bude časom
-- vymieňať a meniť sa má len `eleven_voice_id`, nie deploy.

create table if not exists managed_voices (
  id               uuid primary key default gen_random_uuid(),
  label            text not null,
  eleven_voice_id  text not null,
  description      text not null default '',
  active           boolean not null default true,
  sort             int not null default 0,
  created_at       timestamptz not null default now()
);
create index if not exists managed_voices_active_idx
  on managed_voices (active, sort) where active;

alter table managed_voices enable row level security;
revoke all on managed_voices from anon, authenticated;

-- Klient vidí LEN zapnuté hlasy a LEN to, čo potrebuje na výber.
-- `eleven_voice_id` medzi tým je — bez neho by si nevedel vypočuť ukážku;
-- nie je to tajomstvo, je to identifikátor v našom účte, nie kľúč.
grant select on managed_voices to authenticated;
drop policy if exists managed_voices_read on managed_voices;
create policy managed_voices_read on managed_voices
  for select to authenticated using (active);

-- Zápis len admin, cez RLS (nie cez RPC — je to obyčajný číselník).
grant insert, update, delete on managed_voices to authenticated;
drop policy if exists managed_voices_admin_write on managed_voices;
create policy managed_voices_admin_write on managed_voices
  for all to authenticated using (is_admin()) with check (is_admin());

-- ---------------------------------------------------------------------------
-- (g) behavior — odkiaľ berie hlas
-- ---------------------------------------------------------------------------
--
-- Dva stĺpce namiesto jedného zámerne: keď si klient prepne na náš hlas,
-- nesmie prísť o nastavené ID svojho vlastného. Prepnutie späť ho vráti.

alter table behavior
  add column if not exists voice_source text not null default 'own'
    check (voice_source in ('own', 'managed')),
  add column if not exists managed_voice_id uuid references managed_voices(id);

comment on column behavior.voice_source is
  'own = klientov ElevenLabs kluc a jeho hlas; managed = nas kluc a hlas z managed_voices.';

grant select (voice_source, managed_voice_id),
      insert (voice_source, managed_voice_id),
      update (voice_source, managed_voice_id)
  on behavior to authenticated;

-- ---------------------------------------------------------------------------
-- (h) Sonda
-- ---------------------------------------------------------------------------

do $probe$
declare v_n int; v_def text;
begin
  if not exists (select 1 from pg_constraint
                 where conname = 'accounts_plan_check'
                   and pg_get_constraintdef(oid) like '%vip_lite%') then
    raise exception 'vip_lite nie je v accounts_plan_check';
  end if;

  select pg_get_functiondef(oid) into v_def from pg_proc where proname = 'record_usage';
  if v_def not like '%vip_lite%' then
    raise exception 'record_usage nepozna vip_lite';
  end if;

  select count(*) into v_n from app_config;
  if v_n < 5 then raise exception 'app_config ma % riadkov, cakalo sa aspon 5', v_n; end if;

  if config_value('model_slot_usd') <> 20 then
    raise exception 'cena slotu sa necita z app_config';
  end if;

  if not exists (select 1 from information_schema.columns
                 where table_schema='public' and table_name='behavior'
                   and column_name='voice_source') then
    raise exception 'behavior.voice_source nevznikol';
  end if;

  raise notice 'voices + units + vip_lite OK';
end $probe$;

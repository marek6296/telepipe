-- Fáza admin — roly, balíky, admin RPC, monitoring replík.
--
-- Princíp: klientské (tenantské) policies sa NEROZŠIRUJÚ. Admin nevidí cudzie
-- dáta cez tabuľkové policies, ale výhradne cez security-definer RPC nižšie —
-- povrch útoku je tak jedna funkcia, nie celá tabuľka. Každé RPC si rolu overí
-- samo (`forbidden`), lebo `grant execute ... to authenticated` znamená, že ho
-- môže zavolať ktokoľvek prihlásený.
--
-- POZOR (lekcia z 007): Supabase má `alter default privileges ... grant all on
-- tables to anon, authenticated`, takže KAŽDÁ nová tabuľka v `public` dostane
-- pri vytvorení plné práva pre anon aj authenticated. Preto hneď po `create
-- table` nasleduje `revoke all ... from anon, authenticated`.

-- ---------------------------------------------------------------------------
-- (a) accounts — rola a balík
-- ---------------------------------------------------------------------------

alter table accounts
  add column role text not null default 'user'
    check (role in ('user','admin','superadmin')),
  add column plan text not null default 'free';

-- Marek = superadmin (jediný, kto smie meniť roly).
update accounts set role = 'superadmin' where email = 'cmelo.marek@gmail.com';

-- Sidebar potrebuje rolu prečítať server-side (položka Admin sa inak nezobrazí).
-- `accounts` má z 007 tabuľkový `grant select` pre authenticated, ktorý nové
-- stĺpce pokrýva automaticky; explicitný grant je tu pre čitateľnosť auditu.
-- Zápis nie je: rolu ani balík klient nemení nikdy (žiadny update grant).
grant select (role, plan) on accounts to authenticated;

-- ---------------------------------------------------------------------------
-- (b) models.migration_source — idempotencia migračného skriptu (Task B1)
-- ---------------------------------------------------------------------------

-- Prázdny reťazec = modelka vznikla vo webe. Neprázdny = kľúč zdroja starej
-- inštalácie ('tgai', 'tgmio'), a ten smie existovať práve raz — opakovaný beh
-- skriptu tak nájde existujúci riadok namiesto vytvorenia duplikátu.
alter table models add column migration_source text not null default '';
create unique index models_migration_source_uidx
  on models (migration_source) where migration_source <> '';

-- ---------------------------------------------------------------------------
-- (c) credit_adjustments — audit ručných zásahov do kreditu
-- ---------------------------------------------------------------------------

create table credit_adjustments (
  id bigint generated always as identity primary key,
  account_id uuid not null references accounts(id) on delete cascade,
  admin_id uuid not null references accounts(id) on delete restrict,
  -- Záporná hodnota = korekcia/storno; história sa nikdy neprepisuje.
  amount numeric not null,
  note text not null default '',
  created_at timestamptz not null default now()
);
create index credit_adjustments_account_idx
  on credit_adjustments (account_id, created_at desc);

alter table credit_adjustments enable row level security;
-- Default privileges by inak dali plné práva; audit číta len admin cez RPC.
revoke all on credit_adjustments from anon, authenticated;

-- ---------------------------------------------------------------------------
-- (d) worker_replicas — živý stav workerových replík
-- ---------------------------------------------------------------------------

create table worker_replicas (
  replica_name text primary key,
  last_seen timestamptz not null default now(),
  tenant_count int not null default 0,
  started_at timestamptz not null default now()
);

alter table worker_replicas enable row level security;
-- Píše výhradne worker cez service_role (obchádza RLS a grants má z default
-- privileges), číta admin cez `admin_list_replicas()`. Žiadne policies —
-- pre anon/authenticated je tabuľka neexistujúca.
revoke all on worker_replicas from anon, authenticated;

-- ---------------------------------------------------------------------------
-- (e) Role helpers
-- ---------------------------------------------------------------------------

-- `auth.uid()` je schema-qualified, takže pinned search_path nevadí. Definer
-- je nutný: `accounts` má RLS a bežný používateľ vidí len vlastný riadok
-- (čo by tu síce stačilo, ale helper musí fungovať aj vo vnútri RPC).
create or replace function is_admin()
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
  select exists (
    select 1 from accounts
    where id = auth.uid() and role in ('admin','superadmin')
  );
$$;

create or replace function is_superadmin()
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
  select exists (
    select 1 from accounts
    where id = auth.uid() and role = 'superadmin'
  );
$$;

-- Helpery sú interné — klient sa rolu dozvie zo `select role from accounts`.
revoke execute on function is_admin() from public, anon, authenticated;
revoke execute on function is_superadmin() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- (f) Admin RPC — čítanie
-- ---------------------------------------------------------------------------

create or replace function admin_list_accounts()
returns table (
  id uuid, email text, role text, plan text,
  credit_balance_usd numeric, created_at timestamptz,
  models_count bigint, spend_30d numeric
)
language plpgsql stable security definer
set search_path = public, pg_temp as $$
#variable_conflict use_column
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;

  return query
  select a.id, a.email, a.role, a.plan, a.credit_balance_usd, a.created_at,
         (select count(*) from models m where m.account_id = a.id),
         coalesce((select sum(u.charged_usd) from usage_events u
                    where u.account_id = a.id
                      and u.created_at > now() - interval '30 days'), 0)
  from accounts a
  order by a.created_at;
end;
$$;

create or replace function admin_list_models()
returns table (
  id uuid, account_id uuid, account_email text, name text,
  status text, status_reason text, claimed_by text, heartbeat_at timestamptz,
  msgs_today bigint, spend_today numeric
)
language plpgsql stable security definer
set search_path = public, pg_temp as $$
#variable_conflict use_column
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;

  -- Zámerne LEN metadáta: obsah konverzácií klienta admin cez toto RPC nevidí.
  return query
  select m.id, m.account_id, a.email, m.name,
         m.status, m.status_reason, m.claimed_by, m.heartbeat_at,
         (select count(*) from dm_messages d
           where d.model_id = m.id and d.created_at >= date_trunc('day', now())),
         coalesce((select sum(u.charged_usd) from usage_events u
                    where u.model_id = m.id
                      and u.created_at >= date_trunc('day', now())), 0)
  from models m join accounts a on a.id = m.account_id
  order by a.email, m.created_at;
end;
$$;

create or replace function admin_usage_summary(p_days int default 30)
returns table (
  day date, charged_usd numeric, atlas_cost_usd numeric,
  margin_usd numeric, events bigint
)
language plpgsql stable security definer
set search_path = public, pg_temp as $$
#variable_conflict use_column
declare v_days int := least(greatest(coalesce(p_days, 30), 1), 365);
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;

  -- atlas_cost_usd (naša nákupná cena) je pred klientom skrytý v 008, ale
  -- admin ho vidieť má — marža je jeho čísla.
  return query
  select (date_trunc('day', u.created_at))::date,
         sum(u.charged_usd), sum(u.atlas_cost_usd),
         sum(u.charged_usd) - sum(u.atlas_cost_usd),
         count(*)
  from usage_events u
  where u.created_at >= date_trunc('day', now()) - make_interval(days => v_days - 1)
  group by 1
  order by 1;
end;
$$;

create or replace function admin_list_replicas()
returns table (
  replica_name text, tenant_count int,
  last_seen timestamptz, started_at timestamptz, stale boolean
)
language plpgsql stable security definer
set search_path = public, pg_temp as $$
#variable_conflict use_column
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;

  -- Tick repliky je 30 s (claim_interval_s), 2 minúty ticha = mŕtva replika.
  return query
  select w.replica_name, w.tenant_count, w.last_seen, w.started_at,
         w.last_seen < now() - interval '2 minutes'
  from worker_replicas w
  order by w.last_seen desc;
end;
$$;

-- ---------------------------------------------------------------------------
-- (g) Admin RPC — zápis
-- ---------------------------------------------------------------------------

create or replace function admin_set_role(p_account uuid, p_role text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_current text; v_supers int;
begin
  -- Roly prideľuje LEN superadmin (admin si sám seba nepovýši).
  if not is_superadmin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_role not in ('user','admin','superadmin') then
    raise exception 'invalid role: %', p_role;
  end if;

  select role into v_current from accounts where id = p_account for update;
  if v_current is null then raise exception 'account not found'; end if;
  if v_current = p_role then return v_current; end if;

  -- Posledný superadmin nesmie zmiznúť — inak by roly už nemal kto meniť
  -- (pokrýva aj degradáciu seba samého).
  if v_current = 'superadmin' then
    select count(*) into v_supers from accounts where role = 'superadmin';
    if v_supers <= 1 then
      raise exception 'cannot demote the last superadmin';
    end if;
  end if;

  update accounts set role = p_role where id = p_account;
  return p_role;
end;
$$;

create or replace function admin_set_plan(p_account uuid, p_plan text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_plan not in ('free','starter','pro','custom') then
    raise exception 'invalid plan: %', p_plan;
  end if;
  if not exists (select 1 from accounts where id = p_account) then
    raise exception 'account not found';
  end if;

  update accounts set plan = p_plan where id = p_account;
  return p_plan;
end;
$$;

create or replace function admin_add_credit(
  p_account uuid, p_amount numeric, p_note text default ''
) returns numeric language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_balance numeric;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_amount is null or p_amount = 0 then
    raise exception 'amount must be non-zero';
  end if;

  -- Audit prvý: keby update spadol, transakcia zoberie oboje. Kto komu koľko
  -- a prečo pridal, musí byť dohľadateľné.
  insert into credit_adjustments (account_id, admin_id, amount, note)
  values (p_account, auth.uid(), p_amount, coalesce(p_note, ''));

  update accounts set credit_balance_usd = credit_balance_usd + p_amount
  where id = p_account
  returning credit_balance_usd into v_balance;

  if v_balance is null then raise exception 'account not found'; end if;
  return v_balance;
end;
$$;

-- ---------------------------------------------------------------------------
-- (h) Grants na RPC — anon nikdy, authenticated áno (rolu si overí funkcia)
-- ---------------------------------------------------------------------------

revoke execute on function admin_list_accounts() from public, anon;
revoke execute on function admin_list_models() from public, anon;
revoke execute on function admin_usage_summary(int) from public, anon;
revoke execute on function admin_list_replicas() from public, anon;
revoke execute on function admin_set_role(uuid, text) from public, anon;
revoke execute on function admin_set_plan(uuid, text) from public, anon;
revoke execute on function admin_add_credit(uuid, numeric, text) from public, anon;

grant execute on function admin_list_accounts() to authenticated;
grant execute on function admin_list_models() to authenticated;
grant execute on function admin_usage_summary(int) to authenticated;
grant execute on function admin_list_replicas() to authenticated;
grant execute on function admin_set_role(uuid, text) to authenticated;
grant execute on function admin_set_plan(uuid, text) to authenticated;
grant execute on function admin_add_credit(uuid, numeric, text) to authenticated;

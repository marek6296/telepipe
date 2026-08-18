-- Jednorazove Telegram OTP cisla kupovane z Telepipe kreditov.
--
-- Bezpecnostny model:
--   * browser nikdy nevola VRNUM a nikdy nepozna jeho API kluc ani nakupnu cenu;
--   * kredit sa rezervuje spolu s auditnym riadkom v jednej DB transakcii;
--   * charge/refund maju unikatny ledger zaznam, preto retry nemoze uctovat 2x;
--   * vsetky zapisy aj RPC su iba pre service_role. Prihlaseny klient moze cez
--     RLS citat len vlastne, nesenzitivne stlpce objednavky.

create table telegram_otp_orders (
  id uuid primary key,
  account_id uuid references accounts(id) on delete set null,
  account_email text not null default '',
  idempotency_key uuid not null unique,
  service text not null default 'telegram' check (service = 'telegram'),
  country_code text not null,
  country_name text not null,
  country_flag text not null default '',
  phone_number text,
  status text not null default 'reserved' check (
    status in (
      'reserved', 'provisioning', 'waiting', 'code_received', 'completed',
      'cancelled', 'expired', 'failed'
    )
  ),
  provider_status text not null default '',
  provider_order_id text unique,
  client_reference text not null unique,
  otp_code text,
  provider_price_usd numeric(12, 6) not null check (provider_price_usd > 0),
  charged_credits numeric(12, 6) not null check (charged_credits > 0),
  refunded_credits numeric(12, 6) not null default 0 check (refunded_credits >= 0),
  last_error text not null default '',
  expires_at timestamptz,
  code_received_at timestamptz,
  cancelled_at timestamptz,
  refunded_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (refunded_credits <= charged_credits)
);

create index telegram_otp_orders_account_time_idx
  on telegram_otp_orders (account_id, created_at desc);
create index telegram_otp_orders_active_idx
  on telegram_otp_orders (account_id, status, expires_at)
  where status in ('reserved', 'provisioning', 'waiting', 'code_received');

comment on table telegram_otp_orders is
  'Telepipe objednavky jednorazovych Telegram OTP cisel. Provider data zapisuje iba server.';
comment on column telegram_otp_orders.provider_price_usd is
  'Interna nakupna cena VRNUM. Nema SELECT grant pre authenticated.';
comment on column telegram_otp_orders.idempotency_key is
  'Klientsky UUID jednej nakupnej operacie; retry tej istej operacie ho musi zopakovat.';

create table telegram_otp_credit_events (
  id bigint generated always as identity primary key,
  order_id uuid not null references telegram_otp_orders(id) on delete restrict,
  account_id uuid references accounts(id) on delete set null,
  account_email text not null default '',
  kind text not null check (kind in ('charge', 'refund')),
  amount numeric(12, 6) not null check (amount > 0),
  balance_after numeric not null,
  reason text not null default '',
  created_at timestamptz not null default now(),
  unique (order_id, kind)
);

create index telegram_otp_credit_events_account_time_idx
  on telegram_otp_credit_events (account_id, created_at desc);

comment on table telegram_otp_credit_events is
  'Nemenitelny audit charge/refund udalosti pre Telegram OTP cisla.';

alter table telegram_otp_orders enable row level security;
alter table telegram_otp_credit_events enable row level security;

create policy telegram_otp_orders_owner_select on telegram_otp_orders
  for select to authenticated
  using (account_id = (select auth.uid()));

create policy telegram_otp_credit_events_owner_select on telegram_otp_credit_events
  for select to authenticated
  using (account_id = (select auth.uid()));

-- Projekt ma historicky siroke default privileges. Najprv ich vzdy vynulovat,
-- potom vratit len explicitne citanie bez provider nakupky a internych chyb.
revoke all on telegram_otp_orders, telegram_otp_credit_events from public, anon, authenticated;

grant select (
  id, account_id, idempotency_key, service, country_code, country_name,
  country_flag, phone_number, status, provider_status, otp_code,
  charged_credits, refunded_credits, expires_at, code_received_at,
  cancelled_at, refunded_at, created_at, updated_at
) on telegram_otp_orders to authenticated;

grant select (
  id, order_id, account_id, kind, amount, balance_after, reason, created_at
) on telegram_otp_credit_events to authenticated;

-- Atomicka rezervacia kreditu. Unlimited/VIP sa tu zamerne neuplatnuje:
-- kupene telefonne cislo je externy tovar, nie AI usage benefit planu.
create or replace function reserve_telegram_otp_purchase(
  p_order uuid,
  p_account uuid,
  p_idempotency uuid,
  p_country_code text,
  p_country_name text,
  p_country_flag text,
  p_provider_price numeric,
  p_charged_credits numeric
) returns numeric
language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_balance numeric;
  v_existing telegram_otp_orders;
  v_email text;
begin
  if p_order is null or p_account is null or p_idempotency is null then
    raise exception 'invalid purchase identifier';
  end if;
  if nullif(trim(p_country_code), '') is null
     or nullif(trim(p_country_name), '') is null then
    raise exception 'invalid country';
  end if;
  if p_provider_price is null or p_provider_price <= 0
     or p_charged_credits is null or p_charged_credits <= 0 then
    raise exception 'invalid price';
  end if;

  select * into v_existing
  from telegram_otp_orders
  where idempotency_key = p_idempotency
  for update;

  if found then
    if v_existing.account_id is distinct from p_account
       or v_existing.country_code is distinct from lower(trim(p_country_code))
       or v_existing.charged_credits is distinct from p_charged_credits then
      raise exception 'idempotency key reused for a different purchase';
    end if;
    select credit_balance_usd into v_balance from accounts where id = p_account;
    return v_balance;
  end if;

  select credit_balance_usd, email into v_balance, v_email
  from accounts where id = p_account
  for update;

  if not found then raise exception 'account not found'; end if;
  if v_balance < p_charged_credits then
    raise exception 'insufficient credits' using errcode = 'P0001';
  end if;

  insert into telegram_otp_orders (
    id, account_id, account_email, idempotency_key, country_code,
    country_name, country_flag, client_reference, provider_price_usd,
    charged_credits
  ) values (
    p_order, p_account, coalesce(v_email, ''), p_idempotency,
    lower(trim(p_country_code)), trim(p_country_name), coalesce(p_country_flag, ''),
    'telepipe-' || p_order::text, p_provider_price, p_charged_credits
  );

  update accounts
     set credit_balance_usd = credit_balance_usd - p_charged_credits
   where id = p_account
   returning credit_balance_usd into v_balance;

  insert into telegram_otp_credit_events (
    order_id, account_id, account_email, kind, amount, balance_after, reason
  ) values (
    p_order, p_account, coalesce(v_email, ''), 'charge', p_charged_credits,
    v_balance, 'telegram_otp_purchase'
  );

  return v_balance;
end;
$$;

revoke execute on function reserve_telegram_otp_purchase(
  uuid, uuid, uuid, text, text, text, numeric, numeric
) from public, anon, authenticated;
grant execute on function reserve_telegram_otp_purchase(
  uuid, uuid, uuid, text, text, text, numeric, numeric
) to service_role;

-- Refund je idempotentny: prvy call pripise kredit a zalozi ledger, dalsie len
-- vratia aktualny zostatok. Volat ho smie server az po potvrdeni VRNUM cancelu
-- alebo po jednoznacnom provisioning failure.
create or replace function refund_telegram_otp_purchase(
  p_order uuid,
  p_account uuid,
  p_status text,
  p_reason text default ''
) returns numeric
language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_order telegram_otp_orders;
  v_balance numeric;
begin
  if p_status is null or p_status not in ('cancelled', 'failed') then
    raise exception 'invalid refund status';
  end if;

  select * into v_order
  from telegram_otp_orders
  where id = p_order and account_id = p_account
  for update;

  if not found then raise exception 'order not found'; end if;

  select credit_balance_usd into v_balance
  from accounts where id = p_account
  for update;
  if not found then raise exception 'account not found'; end if;

  if v_order.refunded_at is not null then return v_balance; end if;

  update accounts
     set credit_balance_usd = credit_balance_usd + v_order.charged_credits
   where id = p_account
   returning credit_balance_usd into v_balance;

  update telegram_otp_orders
     set status = p_status,
         refunded_credits = charged_credits,
         refunded_at = now(),
         cancelled_at = case when p_status = 'cancelled' then now() else cancelled_at end,
         last_error = case when p_status = 'failed' then coalesce(p_reason, '') else last_error end,
         updated_at = now()
   where id = p_order;

  insert into telegram_otp_credit_events (
    order_id, account_id, account_email, kind, amount, balance_after, reason
  ) values (
    p_order, p_account, v_order.account_email, 'refund', v_order.charged_credits,
    v_balance, coalesce(nullif(p_reason, ''), p_status)
  );

  return v_balance;
end;
$$;

revoke execute on function refund_telegram_otp_purchase(uuid, uuid, text, text)
  from public, anon, authenticated;
grant execute on function refund_telegram_otp_purchase(uuid, uuid, text, text)
  to service_role;

-- Migracia nesmie potichu prejst s nebezpecnym grantom. Provider nakupka je
-- jediny stlpec, pri ktorom by omyl priamo odhalil nasu marzu.
do $$
begin
  if has_column_privilege('authenticated', 'public.telegram_otp_orders',
                          'provider_price_usd', 'SELECT') then
    raise exception 'authenticated can read VRNUM provider price';
  end if;
  if has_table_privilege('authenticated', 'public.telegram_otp_orders', 'INSERT')
     or has_table_privilege('authenticated', 'public.telegram_otp_orders', 'UPDATE')
     or has_table_privilege('authenticated', 'public.telegram_otp_orders', 'DELETE') then
    raise exception 'authenticated can mutate telegram OTP orders';
  end if;
  if has_function_privilege('authenticated',
      'public.reserve_telegram_otp_purchase(uuid,uuid,uuid,text,text,text,numeric,numeric)',
      'EXECUTE') then
    raise exception 'authenticated can reserve telegram OTP credit';
  end if;
end;
$$;

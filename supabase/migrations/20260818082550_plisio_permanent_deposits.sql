-- Permanent Plisio deposit addresses and idempotent Pipe Coin settlement.
--
-- One address is permanently tied to one Telepipe account + currency. A
-- completed Plisio `pay_in` is credited from the provider-confirmed net USD
-- value. The database applies the bonus ladder and performs the balance
-- update and immutable ledger insert in one transaction.

create table public.crypto_deposit_addresses (
  id uuid primary key default gen_random_uuid(),
  account_id uuid references public.accounts(id) on delete set null,
  deposit_uid text not null,
  pay_currency text not null,
  pay_address text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, pay_currency),
  unique (deposit_uid, pay_currency),
  unique (pay_currency, pay_address)
);

create index crypto_deposit_addresses_lookup_idx
  on public.crypto_deposit_addresses (pay_address, pay_currency);

comment on table public.crypto_deposit_addresses is
  'Permanent Plisio pay-in addresses. One address per account and cryptocurrency.';

create table public.crypto_deposit_events (
  id uuid primary key default gen_random_uuid(),
  -- Plisio txn_id. The unique constraint is the hard idempotency boundary.
  payment_id text not null unique,
  deposit_address_id uuid not null references public.crypto_deposit_addresses(id) on delete restrict,
  account_id uuid references public.accounts(id) on delete set null,
  account_email text not null default '',
  pay_currency text not null,
  pay_address text not null,
  crypto_received numeric(36, 18) not null check (crypto_received > 0),
  -- Net USD value confirmed by Plisio after its processing commission.
  source_usd numeric(18, 8) not null check (source_usd > 0),
  bonus_pct numeric(5, 2) not null check (bonus_pct >= 0 and bonus_pct < 100),
  coins numeric(24, 0) not null check (coins > 0),
  -- Internal balance stays USD; Pipe Coins are its presentation layer.
  credit_usd numeric(18, 6) not null check (credit_usd > 0),
  status text not null,
  tx_urls jsonb not null default '[]'::jsonb check (jsonb_typeof(tx_urls) = 'array'),
  credited boolean not null default false,
  credited_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index crypto_deposit_events_account_time_idx
  on public.crypto_deposit_events (account_id, created_at desc);

comment on table public.crypto_deposit_events is
  'Confirmed Plisio pay-ins and their calculated Pipe Coin credit.';

create table public.crypto_deposit_credit_events (
  id bigint generated always as identity primary key,
  payment_id text not null unique references public.crypto_deposit_events(payment_id) on delete restrict,
  account_id uuid references public.accounts(id) on delete set null,
  source_usd numeric(18, 8) not null check (source_usd > 0),
  bonus_pct numeric(5, 2) not null,
  coins numeric(24, 0) not null check (coins > 0),
  credit_usd numeric(18, 6) not null check (credit_usd > 0),
  balance_after numeric not null,
  created_at timestamptz not null default now()
);

create index crypto_deposit_credit_events_account_time_idx
  on public.crypto_deposit_credit_events (account_id, created_at desc);

alter table public.crypto_deposit_addresses enable row level security;
alter table public.crypto_deposit_events enable row level security;
alter table public.crypto_deposit_credit_events enable row level security;

create policy crypto_deposit_addresses_owner_select on public.crypto_deposit_addresses
  for select to authenticated
  using (account_id = (select auth.uid()));

create policy crypto_deposit_events_owner_select on public.crypto_deposit_events
  for select to authenticated
  using (account_id = (select auth.uid()));

create policy crypto_deposit_credit_events_owner_select on public.crypto_deposit_credit_events
  for select to authenticated
  using (account_id = (select auth.uid()));

revoke all on public.crypto_deposit_addresses, public.crypto_deposit_events,
  public.crypto_deposit_credit_events from public, anon, authenticated;

grant select (
  id, account_id, pay_currency, pay_address, created_at, updated_at
) on public.crypto_deposit_addresses to authenticated;

grant select (
  id, payment_id, account_id, pay_currency, pay_address, crypto_received,
  source_usd, bonus_pct, coins, credit_usd, status, tx_urls, credited,
  credited_at, created_at, updated_at
) on public.crypto_deposit_events to authenticated;

grant select (
  id, payment_id, account_id, source_usd, bonus_pct, coins, credit_usd,
  balance_after, created_at
) on public.crypto_deposit_credit_events to authenticated;

-- Only service_role can call this function. It independently verifies that
-- the address belongs to the supplied account, derives every commercial
-- value from provider-confirmed USD, and credits exactly once.
create or replace function public.settle_crypto_deposit(
  p_payment_id text,
  p_account_id uuid,
  p_deposit_uid text,
  p_pay_currency text,
  p_pay_address text,
  p_crypto_received numeric,
  p_source_usd numeric,
  p_status text,
  p_tx_urls jsonb default '[]'::jsonb
) returns jsonb
language plpgsql security definer
set search_path = '' as $$
declare
  v_address public.crypto_deposit_addresses;
  v_existing public.crypto_deposit_events;
  v_email text;
  v_bonus_pct numeric(5, 2);
  v_coins numeric(24, 0);
  v_credit_usd numeric(18, 6);
  v_balance numeric;
begin
  if nullif(trim(p_payment_id), '') is null
     or p_account_id is null
     or nullif(trim(p_deposit_uid), '') is null
     or nullif(trim(p_pay_currency), '') is null
     or nullif(trim(p_pay_address), '') is null
     or p_crypto_received is null or p_crypto_received <= 0
     or p_source_usd is null or p_source_usd <= 0 or p_source_usd > 1000000000
     or lower(trim(p_status)) not in ('completed', 'finished')
     or p_tx_urls is null or jsonb_typeof(p_tx_urls) <> 'array' then
    raise exception 'invalid deposit settlement arguments';
  end if;

  select * into v_address
    from public.crypto_deposit_addresses
   where account_id = p_account_id
     and deposit_uid = trim(p_deposit_uid)
     and pay_currency = upper(trim(p_pay_currency))
     and pay_address = trim(p_pay_address)
   for update;

  if not found then
    raise exception 'deposit address does not belong to account';
  end if;

  select email into v_email from public.accounts where id = p_account_id for update;
  if not found then
    raise exception 'deposit account no longer exists';
  end if;

  v_bonus_pct := case
    when p_source_usd >= 250 then 20
    when p_source_usd >= 100 then 10
    else 0
  end;
  v_coins := round(p_source_usd * 1000 * (1 + v_bonus_pct / 100));
  v_credit_usd := round(v_coins / 1000, 6);

  insert into public.crypto_deposit_events (
    payment_id, deposit_address_id, account_id, account_email, pay_currency,
    pay_address, crypto_received, source_usd, bonus_pct, coins, credit_usd,
    status, tx_urls
  ) values (
    trim(p_payment_id), v_address.id, p_account_id, v_email,
    upper(trim(p_pay_currency)), trim(p_pay_address), p_crypto_received,
    p_source_usd, v_bonus_pct, v_coins, v_credit_usd,
    lower(trim(p_status)), p_tx_urls
  ) on conflict (payment_id) do nothing;

  select * into v_existing
    from public.crypto_deposit_events
   where payment_id = trim(p_payment_id)
   for update;

  if v_existing.account_id is distinct from p_account_id
     or v_existing.deposit_address_id is distinct from v_address.id then
    raise exception 'payment id is already associated with another account';
  end if;

  if v_existing.credited then
    return jsonb_build_object(
      'found', true,
      'credited', true,
      'status', v_existing.status,
      'coins', v_existing.coins,
      'sourceUsd', v_existing.source_usd
    );
  end if;

  update public.accounts
     set credit_balance_usd = credit_balance_usd + v_existing.credit_usd
   where id = p_account_id
   returning credit_balance_usd into v_balance;

  if not found then
    raise exception 'deposit account no longer exists';
  end if;

  update public.crypto_deposit_events
     set credited = true,
         credited_at = now(),
         updated_at = now()
   where payment_id = trim(p_payment_id);

  insert into public.crypto_deposit_credit_events (
    payment_id, account_id, source_usd, bonus_pct, coins, credit_usd,
    balance_after
  ) values (
    trim(p_payment_id), p_account_id, v_existing.source_usd,
    v_existing.bonus_pct, v_existing.coins, v_existing.credit_usd, v_balance
  );

  return jsonb_build_object(
    'found', true,
    'credited', true,
    'status', v_existing.status,
    'coins', v_existing.coins,
    'sourceUsd', v_existing.source_usd,
    'balance', v_balance
  );
end;
$$;

revoke execute on function public.settle_crypto_deposit(
  text, uuid, text, text, text, numeric, numeric, text, jsonb
) from public, anon, authenticated;
grant execute on function public.settle_crypto_deposit(
  text, uuid, text, text, text, numeric, numeric, text, jsonb
) to service_role;

do $$
begin
  if has_table_privilege('authenticated', 'public.crypto_deposit_addresses', 'INSERT')
     or has_table_privilege('authenticated', 'public.crypto_deposit_addresses', 'UPDATE')
     or has_table_privilege('authenticated', 'public.crypto_deposit_addresses', 'DELETE')
     or has_table_privilege('authenticated', 'public.crypto_deposit_events', 'INSERT')
     or has_table_privilege('authenticated', 'public.crypto_deposit_events', 'UPDATE')
     or has_table_privilege('authenticated', 'public.crypto_deposit_events', 'DELETE') then
    raise exception 'authenticated can mutate permanent deposit records';
  end if;

  if has_function_privilege(
    'authenticated',
    'public.settle_crypto_deposit(text,uuid,text,text,text,numeric,numeric,text,jsonb)',
    'EXECUTE'
  ) then
    raise exception 'authenticated can settle permanent deposits';
  end if;
end;
$$;

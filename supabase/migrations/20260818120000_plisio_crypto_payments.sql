-- Plisio krypto platby — nakup Pipe Coin balikov ($50 = 50 000 coinov).
--
-- Bezpecnostny model (rovnaka filozofia ako telegram_otp_*):
--   * browser nikdy nevola Plisio a nikdy nepozna PLISIO_SECRET_KEY;
--   * pripisanie kreditu robi VYHRADNE settle_crypto_payment() — jedna DB
--     transakcia: row lock na platbe + update zostatku + auditny riadok;
--   * unique constraint v ledgeri je tvrdy backstop proti dvojitemu pripisu
--     (webhook vs. browser poll vs. cron mozu bezat naraz);
--   * vsetky zapisy aj RPC su iba pre service_role; prihlaseny klient cita
--     cez RLS len vlastne platby (na Billing historiu).
--
-- Suma je v DB v USD (`credit_usd`), coiny su len prezentacna vrstva —
-- viď web/lib/coins.ts. `coins` sa uklada informativne a pocita sa pri
-- ZALOZENI faktury, nie pri pripisani: keby sa medzitym zmenili bonusy,
-- platba dostane presne to, co jej bolo slubene.

create table crypto_payments (
  id uuid primary key default gen_random_uuid(),
  -- Plisio txn_id — kluc, cez ktory sa pyta stav a paruje callback.
  payment_id text not null unique,
  account_id uuid references accounts(id) on delete set null,
  account_email text not null default '',
  -- Nas order_number poslany Plisiu (musi byt unikatny per store).
  order_number text not null unique,
  pack_id text not null,
  usd numeric(12, 2) not null check (usd > 0),
  coins numeric not null check (coins > 0),
  -- Kolko USD sa pripise na accounts.credit_balance_usd (= coins / 1000).
  credit_usd numeric(12, 6) not null check (credit_usd > 0),
  pay_currency text not null,
  -- Co sme pouzivatelovi ukazali — adresa a presna krypto suma. Bez toho sa
  -- pripadny spor neda overit na block exploreri.
  pay_address text not null,
  pay_amount numeric not null check (pay_amount > 0),
  -- Plisiov hotovy QR (data URI) — obsahuje adresu aj sumu; ulozeny, aby
  -- reload checkout stranky vedel platbu vykreslit znova.
  qr_code text not null default '',
  status text not null default 'new',
  credited boolean not null default false,
  credited_at timestamptz,
  expire_at timestamptz,
  last_error text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index crypto_payments_account_time_idx
  on crypto_payments (account_id, created_at desc);
-- Cron reconciler chodi len po otvorenych platbach.
create index crypto_payments_open_idx
  on crypto_payments (created_at)
  where credited = false;

comment on table crypto_payments is
  'Plisio faktury na nakup Pipe Coinov. Zapisuje iba server (service_role).';
comment on column crypto_payments.credit_usd is
  'USD suma, ktora sa pri zaplateni pripise na accounts.credit_balance_usd.';

-- Nemenitelny audit pripisov. `payment_id` je unique — jedna platba moze
-- pripisat kredit PRESNE raz, nech uz settle vola ktokolvek a kolkokrat.
create table crypto_credit_events (
  id bigint generated always as identity primary key,
  payment_id text not null unique references crypto_payments(payment_id) on delete restrict,
  account_id uuid references accounts(id) on delete set null,
  account_email text not null default '',
  amount_usd numeric(12, 6) not null check (amount_usd > 0),
  coins numeric not null,
  balance_after numeric not null,
  created_at timestamptz not null default now()
);

create index crypto_credit_events_account_time_idx
  on crypto_credit_events (account_id, created_at desc);

comment on table crypto_credit_events is
  'Nemenitelny audit pripisania Pipe Coinov z Plisio platieb.';

alter table crypto_payments enable row level security;
alter table crypto_credit_events enable row level security;

create policy crypto_payments_owner_select on crypto_payments
  for select to authenticated
  using (account_id = (select auth.uid()));

create policy crypto_credit_events_owner_select on crypto_credit_events
  for select to authenticated
  using (account_id = (select auth.uid()));

-- Projekt ma historicky siroke default privileges — najprv vynulovat, potom
-- vratit len explicitne citanie vlastnych riadkov (RLS + column grant).
revoke all on crypto_payments, crypto_credit_events from public, anon, authenticated;

grant select (
  id, payment_id, account_id, pack_id, usd, coins, pay_currency, pay_address,
  pay_amount, status, credited, credited_at, expire_at, created_at, updated_at
) on crypto_payments to authenticated;

grant select (
  id, payment_id, account_id, amount_usd, coins, balance_after, created_at
) on crypto_credit_events to authenticated;

-- Jedine miesto, kde sa z Plisio platby pripisuje kredit. Cela logika je v
-- jednej transakcii: row lock na platbe vylucuje subezne pripisanie, update
-- zostatku a ledger su atomicke — bud sa stane vsetko, alebo nic (ziadny
-- medzistav "oznacene ako credited, ale kredit nedosiel" ako v starsich
-- dvojfazovych rieseniach).
--
-- p_paid rozhoduje volajuci server po prepocte sum z /operations/{id}
-- (completed | mismatch/expired s received >= expected * 0.99).
create or replace function settle_crypto_payment(
  p_payment_id text,
  p_status text,
  p_paid boolean
) returns jsonb
language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_row crypto_payments;
  v_balance numeric;
begin
  if nullif(trim(p_payment_id), '') is null or nullif(trim(p_status), '') is null then
    raise exception 'invalid settle arguments';
  end if;

  select * into v_row
  from crypto_payments
  where payment_id = p_payment_id
  for update;

  if not found then
    return jsonb_build_object('found', false, 'credited', false, 'status', null);
  end if;

  -- Uz pripisane → terminalny stav sa neprepisuje, len sa vrati.
  if v_row.credited then
    return jsonb_build_object('found', true, 'credited', true, 'status', v_row.status);
  end if;

  -- Nezaplatene → len zaznamenat najnovsi stav.
  if not coalesce(p_paid, false) then
    update crypto_payments
       set status = p_status, updated_at = now()
     where payment_id = p_payment_id;
    return jsonb_build_object('found', true, 'credited', false, 'status', p_status);
  end if;

  -- Zaplatene, ale ucet medzitym zanikol (on delete set null) — kredit nema
  -- kam ist. Nechat credited = false a zapisat dovod; nie je to strata dat,
  -- payment_id + adresa ostavaju overitelne.
  if v_row.account_id is null then
    update crypto_payments
       set status = p_status,
           last_error = 'paid but account no longer exists',
           updated_at = now()
     where payment_id = p_payment_id;
    return jsonb_build_object('found', true, 'credited', false, 'status', p_status,
                              'error', 'account missing');
  end if;

  update accounts
     set credit_balance_usd = credit_balance_usd + v_row.credit_usd
   where id = v_row.account_id
   returning credit_balance_usd into v_balance;

  if not found then
    update crypto_payments
       set status = p_status,
           last_error = 'paid but account no longer exists',
           updated_at = now()
     where payment_id = p_payment_id;
    return jsonb_build_object('found', true, 'credited', false, 'status', p_status,
                              'error', 'account missing');
  end if;

  update crypto_payments
     set status = p_status,
         credited = true,
         credited_at = now(),
         last_error = '',
         updated_at = now()
   where payment_id = p_payment_id;

  insert into crypto_credit_events (
    payment_id, account_id, account_email, amount_usd, coins, balance_after
  ) values (
    p_payment_id, v_row.account_id, v_row.account_email, v_row.credit_usd,
    v_row.coins, v_balance
  );

  return jsonb_build_object('found', true, 'credited', true, 'status', p_status,
                            'balance', v_balance);
end;
$$;

revoke execute on function settle_crypto_payment(text, text, boolean)
  from public, anon, authenticated;
grant execute on function settle_crypto_payment(text, text, boolean)
  to service_role;

-- Migracia nesmie potichu prejst s nebezpecnym grantom.
do $$
begin
  if has_table_privilege('authenticated', 'public.crypto_payments', 'INSERT')
     or has_table_privilege('authenticated', 'public.crypto_payments', 'UPDATE')
     or has_table_privilege('authenticated', 'public.crypto_payments', 'DELETE') then
    raise exception 'authenticated can mutate crypto_payments';
  end if;
  if has_table_privilege('authenticated', 'public.crypto_credit_events', 'INSERT')
     or has_table_privilege('authenticated', 'public.crypto_credit_events', 'UPDATE')
     or has_table_privilege('authenticated', 'public.crypto_credit_events', 'DELETE') then
    raise exception 'authenticated can mutate crypto_credit_events';
  end if;
  if has_function_privilege('authenticated',
      'public.settle_crypto_payment(text,text,boolean)', 'EXECUTE') then
    raise exception 'authenticated can settle crypto payments';
  end if;
end;
$$;

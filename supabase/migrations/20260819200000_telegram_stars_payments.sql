-- Platba cez Telegram Stars — druhá cesta k Pipe Coinom (krypto ostáva hlavná).
--
-- EKONOMIKA (overené v oficiálnej tabuľke Telegramu)
-- --------------------------------------------------
-- Vývojár dostane VŽDY $0,013 za Star. Používateľ v App Store / Play zaplatí
-- ~$0,02 (30 % Apple/Google + ~5 % Telegram). Aby nám z balíka ostalo X USD,
-- faktúra musí znieť na ceil(X / 0,013) Stars.
--
-- Bonusy za objem sa pri Stars NEPOČÍTAJÚ: sú to peniaze navyše, ktoré si
-- môžeme dovoliť pri 1 % poplatku, nie pri 35 %.

-- Kto platil. Nepovinné — slúži na podporu a na to, aby sa dala ďalšia faktúra
-- poslať rovno do jeho chatu namiesto klikania cez odkaz.
alter table accounts add column if not exists telegram_user_id bigint;
create index if not exists accounts_telegram_user_idx
  on accounts (telegram_user_id) where telegram_user_id is not null;

-- Jednorazový token z webu (POZN.: nasledujúca migrácia ho ruší — viď tam).
create table if not exists star_link_tokens (
  token       text primary key,
  account_id  uuid not null references accounts(id) on delete cascade,
  pack_id     text not null default '',
  custom_usd  numeric(10,2),
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null,
  used_at     timestamptz
);
create index if not exists star_link_tokens_account_idx on star_link_tokens (account_id);

-- Ledger platieb. `charge_id` je unikátny → dvojité doručenie updatu nepripíše
-- coiny dvakrát (rovnaký princíp ako crypto_deposit_events).
create table if not exists star_payments (
  charge_id        text primary key,
  account_id       uuid not null references accounts(id) on delete cascade,
  telegram_user_id bigint,
  stars            int  not null,
  coins            bigint not null,
  credited_usd     numeric(12,4) not null,
  pack_id          text not null default '',
  refunded_at      timestamptz,
  created_at       timestamptz not null default now()
);
create index if not exists star_payments_account_idx on star_payments (account_id, created_at desc);

alter table star_link_tokens enable row level security;
revoke all on star_link_tokens from anon, authenticated;

-- Klient VIDÍ svoje platby (nech má doklad), ale nezapisuje nič.
alter table star_payments enable row level security;
revoke all on star_payments from anon, authenticated;
grant select (charge_id, account_id, stars, coins, credited_usd, pack_id, refunded_at, created_at)
  on star_payments to authenticated;
drop policy if exists star_payments_owner_select on star_payments;
create policy star_payments_owner_select on star_payments
  for select to authenticated using (account_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- settle_star_payment — jediné miesto, kde sa za Stars pripisujú coiny
-- ---------------------------------------------------------------------------
create or replace function settle_star_payment(
  p_charge_id text,
  p_account   uuid,
  p_tg_user   bigint,
  p_stars     int,
  p_coins     bigint,
  p_usd       numeric,
  p_pack      text default ''
)
returns boolean language plpgsql security definer
set search_path = public, pg_temp as $fn$
declare v_new boolean := false;
begin
  if p_charge_id is null or p_charge_id = '' then
    raise exception 'charge_id required';
  end if;
  if p_coins <= 0 then
    raise exception 'coins must be positive';
  end if;

  -- Idempotencia stojí na unique primary key, NIE na predchádzajúcom SELECTe:
  -- dva súčasné webhooky by cez „select potom insert" oba prešli.
  insert into star_payments (charge_id, account_id, telegram_user_id, stars, coins,
                             credited_usd, pack_id)
  values (p_charge_id, p_account, p_tg_user, p_stars, p_coins, p_usd, coalesce(p_pack, ''))
  on conflict (charge_id) do nothing;

  get diagnostics v_new = row_count;
  if not v_new then
    return false;  -- už spracované, coiny sa NEPRIPÍŠU druhýkrát
  end if;

  update accounts
     set credit_balance_usd = credit_balance_usd + p_usd,
         telegram_user_id = coalesce(telegram_user_id, p_tg_user)
   where id = p_account;

  return true;
end;
$fn$;

revoke execute on function settle_star_payment(text, uuid, bigint, int, bigint, numeric, text)
  from public, anon, authenticated;
grant execute on function settle_star_payment(text, uuid, bigint, int, bigint, numeric, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- refund_star_payment
-- ---------------------------------------------------------------------------
--
-- Zostatok SMIE ísť do mínusu. Inak by stačilo coiny minúť a potom požiadať
-- o refund — služba zadarmo. Záporný zostatok znamená, že modelka neodpisuje
-- (existujúca kontrola kreditu to už rieši).
create or replace function refund_star_payment(p_charge_id text)
returns boolean language plpgsql security definer
set search_path = public, pg_temp as $fn$
declare v_account uuid; v_usd numeric; v_refunded timestamptz;
begin
  select account_id, credited_usd, refunded_at
    into v_account, v_usd, v_refunded
  from star_payments where charge_id = p_charge_id for update;

  if v_account is null then return false; end if;
  if v_refunded is not null then return false; end if;

  update star_payments set refunded_at = now() where charge_id = p_charge_id;
  update accounts set credit_balance_usd = credit_balance_usd - v_usd
   where id = v_account;
  return true;
end;
$fn$;

revoke execute on function refund_star_payment(text) from public, anon, authenticated;
grant execute on function refund_star_payment(text) to service_role;

-- ---------------------------------------------------------------------------
-- Sonda
-- ---------------------------------------------------------------------------
do $probe$
declare
  v_acc uuid; v_before numeric; v_after numeric;
  v_prvy boolean; v_druhy boolean; v_refund boolean; v_refund2 boolean;
  v_klient_zapise boolean;
  v_reached boolean := false;
begin
  select id, credit_balance_usd into v_acc, v_before
    from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;
  if v_acc is null then
    raise notice 'stars: sonda preskocena';
    return;
  end if;

  begin
    v_prvy  := settle_star_payment('probe-charge-1', v_acc, 12345, 750, 10000, 10.00, 'test');
    v_druhy := settle_star_payment('probe-charge-1', v_acc, 12345, 750, 10000, 10.00, 'test');
    select credit_balance_usd into v_after from accounts where id = v_acc;

    v_refund  := refund_star_payment('probe-charge-1');
    v_refund2 := refund_star_payment('probe-charge-1');

    v_klient_zapise := has_table_privilege('authenticated', 'public.star_payments', 'INSERT');

    v_reached := true;
    raise exception 'stars-sonda-rollback' using errcode = 'P0001';
  exception when raise_exception then
    null;
  end;

  if not v_reached then raise exception 'stars: sonda spadla skor, nez dobehla'; end if;
  if not v_prvy then raise exception 'stars: prva platba nepripisala coiny'; end if;
  if v_druhy then raise exception 'stars: DVOJITE DORUCENIE PRIPISALO COINY DVAKRAT'; end if;
  if v_after <> v_before + 10.00 then
    raise exception 'stars: pripisalo sa % namiesto %', v_after - v_before, 10.00;
  end if;
  if not v_refund then raise exception 'stars: refund neprebehol'; end if;
  if v_refund2 then raise exception 'stars: dvojity refund odpocital dvakrat'; end if;
  if v_klient_zapise then raise exception 'stars: KLIENT SI VIE PRIPISAT PLATBU'; end if;

  if exists (select 1 from star_payments where charge_id like 'probe-%') then
    raise exception 'stars: sonda po sebe nechala platby';
  end if;
  if (select credit_balance_usd from accounts where id = v_acc) <> v_before then
    raise exception 'stars: sonda po sebe nechala zmeneny zostatok';
  end if;
end $probe$;

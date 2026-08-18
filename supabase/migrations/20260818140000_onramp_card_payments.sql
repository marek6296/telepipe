-- OnRamp: druhá cesta k Pipe Coinom — platba kartou (fiat → USDC Polygon)
--
-- Prvá cesta ostáva bezo zmeny: klient pošle krypto na svoju permanentnú
-- Plisio adresu a pripíše sa podľa toho, čo prišlo. Táto je pre ľudí, ktorí
-- krypto poslať nevedia: zaplatia kartou cez checkout.onramp-pay.com, služba
-- pošle USDC (Polygon) na našu adresu a zavolá callback.
--
-- Riadok platby vzniká U NÁS pred presmerovaním na checkout a pripísanie robí
-- tá istá `settle_crypto_payment` ako pri Plisio faktúrach — jedna transakcia,
-- row lock, unique ledger. Preto sa NIKDY nepripíše dvakrát, ani keby callback,
-- browser poll a cron dobehli naraz; presne tá istá poistka ako doteraz.

alter table crypto_payments
  add column if not exists provider text not null default 'plisio',
  -- ipn_token z wallet.php — jediný autoritatívny spôsob, ako sa OnRampu
  -- opýtať „je zaplatené?". Callback sám osebe podpísaný nie je, takže sa mu
  -- neverí: pripisuje sa až po kladnej odpovedi payment-status.php.
  add column if not exists provider_token text not null default '';

alter table crypto_payments drop constraint if exists crypto_payments_provider_check;
alter table crypto_payments add constraint crypto_payments_provider_check
  check (provider in ('plisio', 'onramp'));

-- Reconciler hľadá otvorené riadky podľa provider-a (každý sa refreshuje
-- inou cestou). Parciálny index drží len to, čo naozaj naháňa.
create index if not exists crypto_payments_open_by_provider
  on crypto_payments (provider, created_at)
  where credited = false;

-- Kontrola: stĺpce existujú a klientská rola NEVIDÍ provider_token — nie je
-- to tajomstvo na úrovni kľúča, ale nemá tam čo robiť; klient číta len svoju
-- históriu (usd, coins, status…), na ktorú granty už má.
do $$
begin
  if not exists (
    select 1 from information_schema.columns
     where table_name = 'crypto_payments' and column_name = 'provider_token'
  ) then
    raise exception 'onramp: chýba stĺpec provider_token';
  end if;
  if exists (
    select 1 from information_schema.column_privileges
     where table_name = 'crypto_payments' and grantee = 'authenticated'
       and column_name in ('provider_token')
  ) then
    raise exception 'onramp: provider_token nesmie byť čitateľný klientom';
  end if;
end $$;

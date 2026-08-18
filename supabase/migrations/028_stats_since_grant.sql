-- 028 — chýbajúci column grant na `accounts.stats_since` (oprava 027)
--
-- ČO SA STALO: 027 pridala stĺpec a appka si ho pridala do `getAccount()`, ale
-- grant nie. `accounts` má od migrácie 017 REVOKE na celú tabuľku a granty po
-- jednotlivých stĺpcoch — nový stĺpec teda nie je „verejný odo dňa vzniku",
-- ako to býva inde. PostgREST dotaz padol na „permission denied for column
-- stats_since", `getAccount()` vrátil null a celá appka sa tvárila, že
-- prihlásený človek nemá účet:
--
--   * karta Voice hlásila „No ElevenLabs key on this account yet", hoci kľúč
--     v databáze bol a rozbalí sa (`accountElevenKey` dostal prázdne id)
--   * v hlavičke svietilo 0 Pipe Coins
--
-- Šifra ani kľúče s tým nemali nič spoločné — zlyhal ČÍTACÍ dotaz o krok skôr.

grant select (stats_since) on accounts to authenticated;

-- Kontrola: každý stĺpec, ktorý appka číta v `getAccount()` (lib/models.ts),
-- musí mať grant. Tento zoznam je jediné miesto, kde sa to dá overiť bez
-- spustenia appky — keď doň pribudne stĺpec, pribudne sem aj riadok.
do $$
declare
  v_potrebne text[] := array[
    'id', 'email', 'credit_balance_usd', 'created_at', 'role', 'plan', 'stats_since'
  ];
  v_chyba text;
begin
  select string_agg(c, ', ') into v_chyba
  from unnest(v_potrebne) as c
  where not exists (
    select 1 from information_schema.column_privileges p
     where p.table_name = 'accounts'
       and p.grantee = 'authenticated'
       and p.privilege_type = 'SELECT'
       and p.column_name = c
  );
  if v_chyba is not null then
    raise exception '028: authenticated nemá SELECT na stĺpce accounts: %', v_chyba;
  end if;
end $$;

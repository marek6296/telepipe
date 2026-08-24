-- Prečo je odpoveď odložená: nočný spánok, alebo „ozvem sa o dve hodiny"?
--
-- STALO SA NAOSTRO. `reply_after` je absolútny čas vypočítaný v okamihu zápisu.
-- Pri nočnom zámku sa počíta z otvorenia aktívneho okna — a keď klient okno
-- posunie na skorší začiatok, starý zámok drží ďalej. Modelka šla spať o 01:28
-- so zámkom do 12:12, klient prestavil začiatok na 10:06, fanúšik napísal 10:39
-- a odpoveď mu čakala do 12:12.
--
-- Rozlíšenie treba, lebo tie dve odloženia majú opačné pravidlo:
--   sleep  → nesmie prežiť otvorenie okna (počíta sa z nastavenia, ktoré sa mení)
--   defer  → má platiť presne (je to náhodné „ozvem sa neskôr" vnútri dňa)
--
-- NULL = riadok spred rozlíšenia. Berie sa ako `sleep`, teda tolerantne: horší
-- prípad je, že jedno staré náhodné odloženie vyprší skôr. Opačná voľba by
-- znamenala, že fanúšik čakajúci od rána čaká ďalej.
alter table dm_users
  add column if not exists reply_after_kind text
    check (reply_after_kind in ('sleep', 'defer'));

comment on column dm_users.reply_after_kind is
  'Prečo je odpoveď odložená. `sleep` sa ruší otvorením aktívneho okna, '
  '`defer` platí presne. NULL = starý riadok, berie sa ako sleep.';

do $$
begin
  -- Zapisuje worker (service role). Klient to nesmie prepísať — vedel by si tým
  -- odomknúť odpovede mimo okna.
  if has_column_privilege('authenticated', 'dm_users', 'reply_after_kind', 'UPDATE') then
    raise exception 'reply_after_kind: klient to môže prepísať';
  end if;
  raise notice 'dm_users.reply_after_kind OK';
end $$;

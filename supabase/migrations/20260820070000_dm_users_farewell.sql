-- Posledná správa v chate: kedy sa modelka rozlúčila.
--
-- Koniec okna (`behavior.chat_days`) má dve fázy. Najprv odíde jedna posledná
-- správa — má priveľa správ a ak si chce písať ďalej, nájde ju na jej stránke
-- — a až potom je ticho. Zmiznúť bez slova uprostred rozhovoru je horšie než
-- sa rozlúčiť: človek píše ďalej a čaká, prečo neodpisuje.
--
-- Táto pečiatka je to, čo drží „ticho" tichým. Bez nej by koniec okna znamenal
-- len ďalšiu poslednú správu pri každej jeho ďalšej správe.

alter table dm_users
  add column if not exists farewell_at timestamptz;

comment on column dm_users.farewell_at is
  'Kedy odišla posledná správa pred uzavretím chatu. Kým nie je NULL, modelka '
  'tomuto človeku neodpisuje ani nedáva videné (worker/src/userbot.py).';

do $$
declare
  v_model uuid;
begin
  -- `dm_users` má TABUĽKOVÝ grant SELECT (migrácia 007), takže nový stĺpec ho
  -- dedí. Zápis je vec workera (service role) — klient ho mať nesmie.
  if not has_column_privilege('authenticated', 'dm_users', 'farewell_at', 'SELECT') then
    raise exception 'farewell_at: klient to nevidí';
  end if;
  if has_column_privilege('authenticated', 'dm_users', 'farewell_at', 'UPDATE') then
    raise exception 'farewell_at: klient to môže prepísať';
  end if;

  -- Existujúce konverzácie musia ostať otvorené — inak by ľudia, ktorí práve
  -- píšu, zo dňa na deň prestali dostávať odpovede.
  select model_id into v_model from dm_users where farewell_at is not null limit 1;
  if v_model is not null then
    raise exception 'farewell_at: migrácia niekomu zavrela chat';
  end if;

  raise notice 'dm_users.farewell_at OK';
end $$;

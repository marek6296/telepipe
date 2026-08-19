-- Denné stropy.
--
-- Doteraz existoval len hodinový, takže 40/hod × ~14 h okna dovolilo až 560
-- správ denne — a práve prekročený objem je to, na čo Telegram reaguje.
-- Nameraná reálna špička je 96 správ 6 ľuďom za deň, takže 300 je trojnásobná
-- rezerva a zároveň polovica teoretického stropu.
--
-- `max_messages_per_day` počíta ODOSLANÉ SPRÁVY (bubliny), nie „odpovede":
-- jedna odpoveď sa delí až na tri bubliny a Telegram vidí každú zvlášť. Počítať
-- odpovede by znamenalo strop, ktorý je v skutočnosti trojnásobný.

alter table behavior
  add column if not exists max_messages_per_day int not null default 300;
alter table behavior
  add column if not exists max_new_people_per_day int not null default 20;

comment on column behavior.max_messages_per_day is
  'Koľko správ (bubliniek) smie za 24 h odísť. 0 = bez limitu. Telegram počíta '
  'každú bublinu zvlášť, preto sa nepočítajú „odpovede" ale správy.';
comment on column behavior.max_new_people_per_day is
  'Koľkým NOVÝM ľuďom sa smie za 24 h ozvať sama. 0 = bez limitu.';

-- `behavior` má column-scoped granty (table-level má authenticated len `d`),
-- takže nový stĺpec je skrytý, kým sa vedome nepovolí.
grant select (max_messages_per_day, max_new_people_per_day) on behavior to authenticated;
grant update (max_messages_per_day, max_new_people_per_day) on behavior to authenticated;

do $probe$
declare v_vidi boolean; v_meni boolean; v_default int;
begin
  v_vidi := has_column_privilege('authenticated','public.behavior','max_messages_per_day','SELECT');
  v_meni := has_column_privilege('authenticated','public.behavior','max_messages_per_day','UPDATE');
  if not v_vidi or not v_meni then
    raise exception 'denne stropy: klient ich nevidi alebo nemeni';
  end if;

  select max_messages_per_day into v_default from behavior limit 1;
  if v_default is null or v_default <> 300 then
    raise exception 'denne stropy: default nesedi (je %)', v_default;
  end if;

  -- Poistka: nový strop nesmie byť nižší než nameraná reálna špička, inak by
  -- migrácia ticho umlčala bežiace modelky.
  if 300 < (
    select coalesce(max(pocet), 0) from (
      select count(*) as pocet from dm_messages
       where role = 'assistant'
       group by model_id, date_trunc('day', created_at)
    ) t
  ) then
    raise exception 'denne stropy: default je NIZSI nez realna spicka — umlcal by beziace modelky';
  end if;
end $probe$;

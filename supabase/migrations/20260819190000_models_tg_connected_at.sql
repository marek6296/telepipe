-- Kedy sa Telegram účet pripojil. Potrebné na rozbeh (warmup).
--
-- Čerstvý účet s novým číslom, ktorý od prvej sekundy píše na plný strop, je
-- pre Telegram oveľa podozrivejší než ten istý objem na účte starom rok.
-- Doteraz sa nerozlišovalo vôbec — deň starý účet mal presne tie isté limity
-- ako ročný.
--
-- Backfill na `created_at`: existujúce účty už dávno bežia, takže ich rozbeh má
-- byť dávno za nimi a nesmie ich teraz spomaliť.

alter table models add column if not exists tg_connected_at timestamptz;

update models set tg_connected_at = created_at where tg_connected_at is null;

comment on column models.tg_connected_at is
  'Kedy sa naposledy pripojila Telegram session. Riadi rozbehovú krivku stropov '
  '(warmup): čerstvý účet má nižšie limity než zabehnutý.';

-- `models` má column-scoped granty, takže nový stĺpec je skrytý. Klient ho smie
-- VIDIEŤ (nech vie, prečo je ešte pomalšia), ale nie prepisovať — prepísaním by
-- si rozbeh preskočil.
grant select (tg_connected_at) on models to authenticated;

do $probe$
declare v_bez int; v_meni boolean;
begin
  select count(*) into v_bez from models where tg_connected_at is null;
  if v_bez > 0 then
    raise exception 'warmup: % modeliek ostalo bez tg_connected_at', v_bez;
  end if;

  v_meni := has_column_privilege('authenticated','public.models','tg_connected_at','UPDATE');
  if v_meni then
    raise exception 'warmup: KLIENT SI VIE PRESKOCIT ROZBEH';
  end if;
  if not has_column_privilege('authenticated','public.models','tg_connected_at','SELECT') then
    raise exception 'warmup: klient nevidi, preco je pomalsia';
  end if;
end $probe$;

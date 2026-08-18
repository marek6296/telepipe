-- Telegram fotky na pevné albumy podľa miesta v harmonograme
--
-- Stará logika: voľné textové „collection" + „parts" (dennú dobu si musel
-- klient vypisovať) a náhodný výber. Neprehľadné a ťažko sa riadilo.
--
-- Nová logika: šesť PEVNÝCH albumov, do ktorých klient nahráva. Modelka pošle
-- fotku z albumu podľa toho, KDE práve je (jej harmonogram) — v gyme fotku
-- z gymu, v posteli večer fotku „bed night". Album sa v jednom chate použije
-- najviac raz; každá fotka najviac raz.
--
-- FANVUE SA TOHTO NETÝKA: Fanvue má vlastný vault (`fv_media`), tie fotky
-- posiela Fanvue API a táto migrácia sa ich nedotýka.
--
-- Albumy (kľúče, natvrdo — nie voľný text, nech sa nedá vytvoriť „gzm"):
--   home        · doma (home / kitchen / bathroom)
--   gym         · v gyme
--   city        · vonku, v meste (outside / cafe / car)
--   bed_morning · v posteli ráno/cez deň
--   bed_night   · v posteli večer/v noci
--   universal   · záloha, keď nič nesedí

alter table photos add column if not exists folder text not null default 'universal';

alter table photos drop constraint if exists photos_folder_check;
alter table photos add constraint photos_folder_check
  check (folder in ('home', 'gym', 'city', 'bed_morning', 'bed_night', 'universal'));

-- Nový stĺpec je krytý plným grantom tabuľky, ale `photos` má aj column-level
-- granty — pridáme folder explicitne, nech sa nestane to, čo pri stats_since.
grant select (folder), insert (folder), update (folder) on photos to authenticated;

-- ČISTÝ ŠTART. Stará logika (collection/parts) sa nedá spoľahlivo premapovať
-- na albumy — každý album potrebuje aspoň 1–2 fotky a to je rozhodnutie
-- klienta, nie stroja. Klient nahrá fotky nanovo do albumov. `photo_sends`
-- (kto čo videl) padá kaskádou — a to je správne: nové fotky = nová história.
delete from photos;

-- Prepínač posielania fotiek na Telegrame. DEFAULT VYPNUTÝ: kým klient nemá
-- v albumoch fotky, nemá sa čo posielať. Web ho pustí zapnúť len keď fotky sú.
alter table behavior add column if not exists photos_enabled boolean not null default false;

grant select (photos_enabled), insert (photos_enabled), update (photos_enabled)
  on behavior to authenticated;

do $$
begin
  if not exists (
    select 1 from information_schema.columns
     where table_name = 'photos' and column_name = 'folder'
  ) then
    raise exception 'photo albums: chyba stlpec folder';
  end if;
  if not exists (
    select 1 from information_schema.columns
     where table_name = 'behavior' and column_name = 'photos_enabled'
  ) then
    raise exception 'photo albums: chyba stlpec photos_enabled';
  end if;
  -- Granty na oba nové stĺpce pre klientsku rolu.
  if not exists (
    select 1 from information_schema.column_privileges
     where table_name='photos' and grantee='authenticated'
       and column_name='folder' and privilege_type='UPDATE'
  ) then
    raise exception 'photo albums: chyba grant na photos.folder';
  end if;
  if not exists (
    select 1 from information_schema.column_privileges
     where table_name='behavior' and grantee='authenticated'
       and column_name='photos_enabled' and privilege_type='UPDATE'
  ) then
    raise exception 'photo albums: chyba grant na behavior.photos_enabled';
  end if;
end $$;

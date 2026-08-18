-- 029 — rozsahy, v ktorých sa hlasovky pohybujú, si nastavuje klient
--
-- Doteraz boli hlasitosť aj dĺžka ticha na okrajoch konštanty v kóde
-- (`livevoice.NOTE_MIN/MAX`, `LEAD_*`, `TAIL_*`). Znamenalo to, že „tichšie"
-- alebo „dlhšia pauza" bol deploy workera, nie posunutie posuvníka — a keďže
-- správne číslo je vec ucha, nie merania, patrí to klientovi do ruky.
--
-- Sú to ROZSAHY, nie hodnoty. Každá hlasovka si z nich vylosuje vlastné číslo;
-- práve to je dôvod, prečo séria hlasoviek neznie ako stroj. Keby to bola jedna
-- hodnota, vrátili by sme sa presne k tomu, čo sa dnes celý deň opravovalo.
--
-- Defaulty sú hodnoty, na ktorých sme sa dnes ustálili pri ladení so Simonou.

alter table behavior
  add column if not exists voice_volume_min numeric not null default 0.07,
  add column if not exists voice_volume_max numeric not null default 0.17,
  add column if not exists voice_lead_min   numeric not null default 1.0,
  add column if not exists voice_lead_max   numeric not null default 3.0,
  add column if not exists voice_tail_min   numeric not null default 1.5,
  add column if not exists voice_tail_max   numeric not null default 4.0;

-- Medze sú tam, kde sa to ešte dá počúvať. Hlasitosť nad 0.5 už limiter aj tak
-- zrovná a pod 0.02 nie je hlasovka počuť; ticho nad 6 s pôsobí ako zabudnutý
-- telefón, nie ako nadýchnutie.
alter table behavior drop constraint if exists behavior_voice_ranges_check;
alter table behavior add constraint behavior_voice_ranges_check check (
  voice_volume_min > 0     and voice_volume_max <= 0.60
  and voice_lead_min >= 0  and voice_lead_max <= 6.0
  and voice_tail_min >= 0  and voice_tail_max <= 8.0
  -- Prevrátený rozsah by `random.uniform` nezhodil, len by ticho vracal čísla
  -- mimo toho, čo klient videl na obrazovke.
  and voice_volume_min <= voice_volume_max
  and voice_lead_min   <= voice_lead_max
  and voice_tail_min   <= voice_tail_max
);

-- GRANTY. `behavior` má revoke na celú tabuľku a granty po stĺpcoch — nový
-- stĺpec teda NIE JE čitateľný odo dňa vzniku. Zabudnutý grant na
-- `accounts.stats_since` dnes zhasol pol dashboardu, tak nech je to tu naraz.
grant select (voice_volume_min, voice_volume_max, voice_lead_min,
              voice_lead_max, voice_tail_min, voice_tail_max) on behavior to authenticated;
grant insert (voice_volume_min, voice_volume_max, voice_lead_min,
              voice_lead_max, voice_tail_min, voice_tail_max) on behavior to authenticated;
grant update (voice_volume_min, voice_volume_max, voice_lead_min,
              voice_lead_max, voice_tail_min, voice_tail_max) on behavior to authenticated;

do $$
declare
  v_stlpce text[] := array['voice_volume_min','voice_volume_max','voice_lead_min',
                           'voice_lead_max','voice_tail_min','voice_tail_max'];
  v_pravo text;
  v_chyba text;
begin
  foreach v_pravo in array array['SELECT','INSERT','UPDATE'] loop
    select string_agg(c, ', ') into v_chyba
    from unnest(v_stlpce) as c
    where not exists (
      select 1 from information_schema.column_privileges p
       where p.table_name = 'behavior' and p.grantee = 'authenticated'
         and p.privilege_type = v_pravo and p.column_name = c
    );
    if v_chyba is not null then
      raise exception '029: chýba % na stĺpcoch: %', v_pravo, v_chyba;
    end if;
  end loop;
end $$;

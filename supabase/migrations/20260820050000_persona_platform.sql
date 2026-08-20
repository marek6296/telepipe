-- Kam modelka ťahá ľudí: Fanvue alebo OnlyFans.
--
-- ČO SA MENÍ A ČO NIE — TOTO JE CELÁ PODSTATA
-- -------------------------------------------
-- Mení sa JEDINÉ: ako svoju stránku POMENUJE, keď sa jej na ňu fanúšik spýta.
--
-- Logika funnelu sa nemení ani o riadok a nikdy nebola viazaná na Fanvue:
--   • prompt hovorí „tvoja stránka", meno platformy v ňom nikdy nebolo
--   • `funnel.py` rozpoznáva `fanvue` aj `onlyfans` rovnako, od začiatku
--   • `checkout.py` cudzí odkaz nechá tak, takže OnlyFans link prejde celý
--
-- Test `test_rozdiel_je_iba_v_pomenovani` to drží: prompty pre obe platformy
-- sa smú líšiť VÝHRADNE v sekcii o názve stránky.
--
-- ČO OnlyFans NEDOSTANE
-- ---------------------
-- Sledovanie fanúšika cez `client_reference_id` funguje len pri Fanvue —
-- prepája človeka z Telegramu s jeho účtom po zaplatení. OnlyFans na to nemá
-- API a predstierať to by znamenalo tichú stratu dát.
--
-- A hlavne: `persona.platform` NIE JE to isté ako pripojené Fanvue. Modelka
-- môže ťahať na OnlyFans a Fanvue nemať pripojené vôbec — sú to dve nezávislé
-- veci a miešať ich by znamenalo, že sa nedá mať jedno bez druhého.

alter table persona
  add column if not exists platform text not null default 'fanvue';

alter table persona drop constraint if exists persona_platform_check;
alter table persona add constraint persona_platform_check
  check (platform in ('fanvue', 'onlyfans', 'other'));

comment on column persona.platform is
  'Kam ťahá ľudí: fanvue / onlyfans / other. Ovplyvňuje LEN pomenovanie '
  'stránky v jej reči. `other` = má stránku inde a nemenuje ju.';

do $$
declare
  v_model uuid;
  v_ok boolean := false;
  v_inych int;
begin
  -- Existujúce modelky musia ostať na fanvue — inak by sa niekomu zmenilo, čo
  -- modelka o sebe hovorí, bez toho aby o tom vedel.
  select count(*) into v_inych from persona where platform <> 'fanvue';
  if v_inych > 0 then
    raise exception 'platform: % person nie je na fanvue', v_inych;
  end if;

  select model_id into v_model from persona limit 1;
  if v_model is not null then
    begin
      update persona set platform = 'pornhub' where model_id = v_model;
    exception when check_violation then v_ok := true;
    end;
    if not v_ok then
      raise exception 'platform: neplatná hodnota prešla cez CHECK';
    end if;
  end if;

  if not has_column_privilege('authenticated', 'persona', 'platform', 'UPDATE') then
    raise exception 'platform: klient nemôže prepnúť platformu';
  end if;

  raise notice 'persona.platform OK';
end $$;

-- Easy agent — prepínač, koľko si klient nastavuje sám.
--
-- ČO TO RIEŠI
-- -----------
-- Persona má šesť textových polí (backstory, tón, štýl, hranice, funnel,
-- ukážky) a práve na nich to väčšine ľudí zamrzne. `behavior` aj
-- `model_schedule` pritom majú kompletné defaulty priamo v databáze, takže
-- celý týždenný život aj ľudské rytmy nová modelka dostane sama. Chýba len
-- tých šesť polí.
--
-- `easy` znamená: preset ich vyplní a formulár ukáže len základy (meno, vek,
-- mesto, jazyky, odkaz). `personal` je pôvodné správanie.
--
-- WORKER O TOMTO STĹPCI NEVIE A VEDIEŤ NEMÁ
-- -----------------------------------------
-- Preset sa zapíše do tabuľky `persona` a číta sa odtiaľ presne ako čokoľvek,
-- čo klient napíše ručne. Vďaka tomu tento prepínač nemôže rozbiť bežiacu
-- modelku — mení dáta, nie správanie. Keby o ňom worker vedel, vzniklo by
-- druhé miesto, kde sa rozhoduje o prompte.
--
-- DEFAULT JE `personal` A JE TO POISTKA
-- -------------------------------------
-- Všetky existujúce modelky sú nastavené ručne a preset sa k nim nesmie
-- priblížiť. Sonda to overuje výslovne.

alter table models
  add column if not exists setup_mode text not null default 'personal';

alter table models drop constraint if exists models_setup_mode_check;
alter table models add constraint models_setup_mode_check
  check (setup_mode in ('personal', 'easy'));

comment on column models.setup_mode is
  'personal = klient si personu píše sám (pôvodné správanie, default). '
  'easy = šesť textových polí persony vyplnil preset a formulár ukazuje len '
  'základy. Worker o tomto stĺpci NEVIE — preset sa zapíše do persona a odtiaľ '
  'sa číta rovnako ako čokoľvek, čo klient napíše ručne.';

grant select (setup_mode), update (setup_mode) on models to authenticated;

do $$
declare
  v_model uuid;
  v_ok boolean := false;
  v_personal int;
begin
  -- (1) VŠETKY existujúce modelky musia ostať personal.
  select count(*) into v_personal from models where setup_mode <> 'personal';
  if v_personal > 0 then
    raise exception 'setup_mode: % existujúcich modeliek nie je personal', v_personal;
  end if;

  -- (2) Nezmysel musí spadnúť, inak by UI vetvilo na hodnote, ktorú nepozná.
  select id into v_model from models limit 1;
  if v_model is not null then
    begin
      update models set setup_mode = 'turbo' where id = v_model;
    exception when check_violation then v_ok := true;
    end;
    if not v_ok then
      raise exception 'setup_mode: neplatná hodnota prešla cez CHECK';
    end if;
  end if;

  -- (3) Klient si mód prepína sám — bez grantu by prepínač ticho nerobil nič.
  if not has_column_privilege('authenticated', 'models', 'setup_mode', 'UPDATE')
     or not has_column_privilege('authenticated', 'models', 'setup_mode', 'SELECT') then
    raise exception 'setup_mode: klient nemôže prepnúť mód';
  end if;

  raise notice 'setup_mode OK — všetky existujúce modelky ostávajú personal';
end $$;

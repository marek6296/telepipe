-- Jazyky modelky ako ŠTRUKTÚRA, nie ako voľný text.
--
-- ČO BOLO
-- -------
-- `persona.language` („reply language") a `persona.languages` („languages she
-- knows") sú voľné textové polia. Klient do nich napíše čokoľvek, prompt to
-- vloží doslova a nikto nevie, čo z toho model pochopí. Úroveň sa nedala zadať
-- vôbec — v prompte bola natvrdo B1 pre každý cudzí jazyk.
--
-- ČO JE TERAZ
-- -----------
-- `lang_primary` — jeden jazyk, ktorým píše plynulo a primárne.
-- `lang_extra`   — najviac tri ďalšie, každý s úrovňou (A1–C2).
--
-- Staré textové polia OSTÁVAJÚ a nemažú sa. Sú to jej vlastné slová o tom, ako
-- s jazykmi narába („s Nemcami radšej po anglicky"), a to sa do kódu jazyka
-- nezmestí. Prompt ich skladá spolu: štruktúra dá tvrdé fakty, text dá nuansu.
--
-- ČO SA TU NEVALIDUJE A PREČO
-- ---------------------------
-- Zoznam ponúkaných jazykov NIE JE v databáze. Žije v appke (`lib/languages.ts`
-- a `worker/src/jazyky.py`), lebo tam sa aj vykresľuje a prekladá do promptu.
-- Tretia kópia v CHECK constraint by sa rozišla ako prvá. Databáza preto stráži
-- TVAR (kód, úroveň, počet, duplicity) — nie katalóg.

-- POZNÁMKA K TVARU KONTROLY
-- -------------------------
-- Všetko je v jednej funkcii a jednom CHECK zámerne: `check` nesmie obsahovať
-- poddotaz, a bez poddotazu sa pole ani duplicity skontrolovať nedajú. Prvý beh
-- tejto migrácie na tom spadol.

-- ---------------------------------------------------------------------------
-- (a) Kontrola tvaru
-- ---------------------------------------------------------------------------

create or replace function persona_langs_ok(p_primary text, p_extra jsonb)
returns boolean language sql immutable as $$
  select
    coalesce(p_primary, '') ~ '^[a-z]{2}$'
    and jsonb_typeof(p_extra) = 'array'
    and jsonb_array_length(p_extra) <= 3
    and not exists (
      select 1 from jsonb_array_elements(p_extra) e
      where jsonb_typeof(e.value) <> 'object'
         or (select count(*) from jsonb_object_keys(e.value)) <> 2
         or not (e.value ? 'code') or not (e.value ? 'level')
         or e.value ->> 'code' !~ '^[a-z]{2}$'
         or (e.value ->> 'level') not in ('A1','A2','B1','B2','C1','C2')
         -- Primárny jazyk medzi vedľajšími je rozpor: raz plynulo, raz na B1.
         or e.value ->> 'code' = p_primary
    )
    and (
      select count(distinct e.value ->> 'code') = jsonb_array_length(p_extra)
      from jsonb_array_elements(p_extra) e
    );
$$;

comment on function persona_langs_ok(text, jsonb) is
  'Tvar jazykov persony: primárny kód + pole najviac 3 objektov {code,level}, '
  'bez duplicít a bez primárneho medzi nimi. Katalóg ponúkaných jazykov tu NIE '
  'JE — ten žije v appke (lib/languages.ts a worker/src/jazyky.py).';

-- ---------------------------------------------------------------------------
-- (b) Stĺpce
-- ---------------------------------------------------------------------------

alter table persona
  add column if not exists lang_primary text not null default 'en',
  add column if not exists lang_extra jsonb not null default '[]'::jsonb;

alter table persona drop constraint if exists persona_langs_check;
alter table persona add constraint persona_langs_check
  check (persona_langs_ok(lang_primary, lang_extra));

comment on column persona.lang_primary is
  'Jazyk, ktorým píše plynulo a primárne. ISO 639-1, dve malé písmená.';
comment on column persona.lang_extra is
  'Najviac 3 ďalšie jazyky: [{"code":"de","level":"B1"}]. Úroveň riadi, ako '
  'dobre v ňom píše — B1 znamená jednoduché vety a občasná chyba.';

-- `persona` má tabuľkový grant pre `authenticated` (na rozdiel od `accounts`),
-- takže nové stĺpce sú editovateľné rovno a je to tu správne — všetky polia
-- persony si klient nastavuje sám. Sonda to overuje, nech sa to nezmení potichu.

-- ---------------------------------------------------------------------------
-- (c) Sonda
-- ---------------------------------------------------------------------------

do $$
declare
  v_model uuid;
  v_ok boolean;
  v_zle int := 0;
  v_zla_hodnota jsonb;
  v_reached boolean := false;
begin
  select model_id into v_model from persona limit 1;
  if v_model is null then
    raise notice 'jazyky: sonda preskočená — žiadna persona';
  else
    begin
      -- (1) Platné nastavenie musí prejsť.
      update persona set lang_primary = 'en',
                         lang_extra = '[{"code":"de","level":"B1"},{"code":"es","level":"B1"}]'::jsonb
       where model_id = v_model;

      -- (2) Každý z týchto tvarov musí spadnúť. Keby prešiel čo i len jeden,
      --     do promptu sa dostane nezmysel a modelka začne tvrdiť, že vie
      --     jazyk, ktorý appka nepozná.
      foreach v_zla_hodnota in array array[
        '"nie je pole"'::jsonb,
        '[{"code":"de","level":"Z9"}]'::jsonb,
        '[{"code":"deu","level":"B1"}]'::jsonb,
        '[{"code":"DE","level":"B1"}]'::jsonb,
        '[{"code":"de"}]'::jsonb,
        '[{"code":"de","level":"B1","tajne":"x"}]'::jsonb,
        '[{"code":"de","level":"B1"},{"code":"de","level":"C1"}]'::jsonb,
        '[{"code":"en","level":"B1"}]'::jsonb,
        '[{"code":"aa","level":"B1"},{"code":"bb","level":"B1"},{"code":"cc","level":"B1"},{"code":"dd","level":"B1"}]'::jsonb
      ] loop
        begin
          update persona set lang_extra = v_zla_hodnota where model_id = v_model;
          v_zle := v_zle + 1;  -- prešlo, hoci nemalo
        exception when check_violation then null;
        end;
      end loop;

      -- (3) Neplatný primárny kód musí spadnúť tiež.
      v_ok := false;
      begin
        update persona set lang_primary = 'XX' where model_id = v_model;
      exception when check_violation then v_ok := true;
      end;

      v_reached := true;
      raise exception 'jazyky-probe-rollback';
    exception when others then
      if sqlerrm <> 'jazyky-probe-rollback' then raise; end if;
    end;

    if not v_reached then raise exception 'jazyky: sonda nedobehla'; end if;
    if v_zle > 0 then
      raise exception 'jazyky: % nepodarených tvarov prešlo cez CHECK', v_zle;
    end if;
    if not v_ok then
      raise exception 'jazyky: neplatný primárny kód prešiel';
    end if;
  end if;

  -- (4) Klient si persona polia nastavuje sám — keby tento grant zmizol,
  --     formulár by prestal fungovať a nikto by nevedel prečo.
  if not has_column_privilege('authenticated', 'persona', 'lang_primary', 'UPDATE')
     or not has_column_privilege('authenticated', 'persona', 'lang_extra', 'UPDATE') then
    raise exception 'jazyky: klient nemôže nastaviť jazyky';
  end if;

  raise notice 'jazyky: štruktúra OK';
end $$;

-- „Ktorým z jej kontaktov smie písať" prestáva byť vec repliky a stáva sa
-- vecou modelky.
--
-- ČO SA STALO
-- ----------
-- Marekov kamarát (chat 6977754097) napísal Simone a nedostal odpoveď, kým
-- Marek odpovede dostával. Príčina je `userbot.py:203-210`: odosielateľ, ktorý
-- je v kontaktoch účtu, sa preskočí, keď je `skip_contacts` zapnuté a nie je
-- vo `contact_exceptions`. Majiteľa filter obchádza (`not is_owner and …`) — a
-- presne preto to vyzeralo, že produkt funguje jednému a druhému nie.
--
-- Obe hodnoty čítal `Config.from_env` z PROCESNÉHO prostredia (`SKIP_CONTACTS`,
-- default true; `CONTACT_EXCEPTIONS`), teda jedna hodnota pre všetkých tenantov
-- na replike. Na Railway neboli nastavené vôbec, takže každá modelka ticho
-- bežala s „ignoruj moje kontakty". V starom jednotenantovom projekte mal Marek
-- `SKIP_CONTACTS=false` a pri sťahovaní do telepipe sa to stratilo.
--
-- PREČO PER-MODEL A NIE OPRAVA ENV
-- --------------------------------
-- „Ktorí moji známi ju smú vyskúšať" je z podstaty vec jedného účtu: každý
-- klient má inú rodinu a iných kamarátov. Globálna premenná to nevie vyjadriť a
-- pri druhom klientovi s inou potrebou nutne pokazí prvého. Env ostáva len ako
-- default pre riadok, ktorý stĺpce ešte nemá (rollout) — pravda je odteraz v
-- riadku, nie v prostredí.
--
-- PREČO 023b A NIE 023
-- --------------------
-- 023 je už nasadená. Dopísať do nej ďalšie príkazy by znamenalo súbor, ktorý
-- sa nezhoduje s tým, čo v databáze naozaj prebehlo. Repo má na to zavedený tvar
-- — 007b, 014b, 018b, 022b — a toto je presne ten prípad.
--
-- SEED: DEFAULT JE BEZPEČNÝ, EXISTUJÚCE RIADKY SA NESMÚ HNÚŤ
-- ---------------------------------------------------------
-- Nová modelka dostane `true` (nepíš rodine a známym) — to je správne
-- východisko pre niekoho, kto o filtri ešte nepočul. Existujúce riadky sa ale
-- musia správať PRESNE ako doteraz, a dnes je efektívna hodnota `false` (env je
-- tak nastavený). Preto sa všetkým riadkom, ktoré v čase migrácie existujú,
-- nastaví `false`. Zámerne bez menného zoznamu: kto v tej chvíli beží, ten sa
-- pri prepnutí zdroja pravdy nesmie zmeniť, a to platí aj o draftoch.

-- ---------------------------------------------------------------------------
-- (a) Stĺpce
-- ---------------------------------------------------------------------------

alter table models
  add column if not exists skip_contacts boolean not null default true,
  add column if not exists contact_exceptions bigint[] not null default '{}';

-- Zachovanie súčasného správania pri prepnutí zdroja pravdy z env do riadku.
-- `updated_at` sa zámerne NEDOTÝKA: nie je to zmena, ktorú urobil klient.
update models set skip_contacts = false;

-- Výnimka je chat id, nie ľubovoľné číslo. Nula nie je platné Telegram id a
-- prázdne pole je bežný stav, takže `check` rieši len obsah.
alter table models
  add constraint models_contact_exceptions_check
  check (not (contact_exceptions @> array[0::bigint]));

-- ---------------------------------------------------------------------------
-- (b) Granty — celý zoznam naraz, rovnako ako v 023
-- ---------------------------------------------------------------------------
--
-- Revoke-then-grant, nech je zoznam povolených stĺpcov na jednom mieste
-- čitateľný celý. Zoznam pre SELECT je ten z 007 + `model_type` (018) + tieto
-- dva; zoznam pre UPDATE je ten z 023 + tieto dva. Tajomstvá (`*_enc`) v ani
-- jednom nie sú a byť nesmú.

revoke select, update on models from anon, authenticated;

grant select (id, account_id, name, model_type, status, status_reason,
              claimed_by, heartbeat_at, tg_api_id, tg_api_hash, owner_chat_id,
              owner_as_client, voice_only_ids, skip_contacts, contact_exceptions,
              created_at, updated_at)
  on models to authenticated;

grant update (name, tg_api_id, owner_chat_id, owner_as_client,
              skip_contacts, contact_exceptions, updated_at)
  on models to authenticated;

-- ---------------------------------------------------------------------------
-- (c) Poistky
-- ---------------------------------------------------------------------------

do $$
declare
  v_secret text;
  v_probe uuid;
  v_account uuid;
  v_skip_before boolean;
  v_exc_before bigint[];
  v_ok boolean := false;
  v_reached boolean := false;
  v_left int;
begin
  -- (1) Nové stĺpce musia byť čitateľné aj zapisovateľné, inak je UI slepé.
  foreach v_secret in array array['skip_contacts', 'contact_exceptions'] loop
    if not has_column_privilege('authenticated', 'public.models', v_secret, 'SELECT')
       or not has_column_privilege('authenticated', 'public.models', v_secret, 'UPDATE') then
      raise exception 'models.% nemá klientský select/update grant', v_secret;
    end if;
  end loop;

  -- (2) Revoke zhodil VŠETKY stĺpcové granty — tajomstvá sa nesmeli vrátiť.
  foreach v_secret in array array[
    'account_id', 'model_type', 'status', 'status_reason',
    'claimed_by', 'claimed_until', 'heartbeat_at',
    'tg_api_hash', 'tg_session_enc', 'control_bot_token_enc'
  ] loop
    if not exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = 'models' and column_name = v_secret
    ) then
      continue;
    end if;
    if has_column_privilege('authenticated', 'public.models', v_secret, 'UPDATE')
       or has_column_privilege('anon', 'public.models', v_secret, 'UPDATE') then
      raise exception 'models.% je pre klienta zapisovateľný', v_secret;
    end if;
  end loop;

  -- Šifrované tajomstvá von nejdú ani majiteľovi — grant select ich nesmie
  -- obsahovať ani omylom.
  foreach v_secret in array array['tg_session_enc', 'control_bot_token_enc'] loop
    if has_column_privilege('authenticated', 'public.models', v_secret, 'SELECT')
       or has_column_privilege('anon', 'public.models', v_secret, 'SELECT') then
      raise exception 'models.% je pre klienta čitateľný — tajomstvo uniklo', v_secret;
    end if;
  end loop;

  if has_table_privilege('anon', 'public.models', 'SELECT')
     or has_table_privilege('anon', 'public.models', 'UPDATE') then
    raise exception 'anon má prístup na models';
  end if;

  -- (3) Seed: po migrácii nesmie ostať existujúci riadok s `true`, inak by sa
  --     niekomu naživo vyplo odpovedanie kontaktom.
  select count(*) into v_left from models where skip_contacts;
  if v_left > 0 then
    raise exception 'seed zlyhal — % existujúcich modeliek má skip_contacts = true', v_left;
  end if;

  -- (4) Živá skúška: majiteľ si obe hodnoty naozaj prepne (grant + RLS).
  --     Všetko sa zahodí sentinel výnimkou — vnútorný blok je savepoint.
  select m.id, m.account_id, m.skip_contacts, m.contact_exceptions
    into v_probe, v_account, v_skip_before, v_exc_before
  from models m
  order by (m.status <> 'draft'), m.created_at
  limit 1;

  if v_probe is null then
    raise notice 'sonda preskočená — v models nie je ani jeden riadok';
  else
    begin
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_account, 'role', 'authenticated')::text,
                         true);
      set local role authenticated;

      update models
         set skip_contacts = not v_skip_before,
             contact_exceptions = array[6977754097::bigint],
             updated_at = now()
       where id = v_probe;

      select skip_contacts is distinct from v_skip_before
             and contact_exceptions = array[6977754097::bigint]
        into v_ok
      from models where id = v_probe;

      v_reached := true;
      raise exception 'contacts-sonda-rollback' using errcode = 'P0001';
    exception when others then
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then
      raise exception 'sonda spadla skôr, než dobehla — grant alebo RLS nepustili update';
    end if;
    if not v_ok then
      raise exception 'skip_contacts/contact_exceptions sa majiteľovi nezmenili';
    end if;
    if exists (
      select 1 from models
      where id = v_probe
        and (skip_contacts is distinct from v_skip_before
             or contact_exceptions is distinct from v_exc_before)
    ) then
      raise exception 'sonda po sebe nechala zmenenú modelku %', v_probe;
    end if;
  end if;
end $$;

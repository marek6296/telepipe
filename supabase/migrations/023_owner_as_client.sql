-- Testovací chat — `models.owner_as_client` konečne aj z dashboardu.
--
-- ČO TEN STĹPEC ROBÍ
-- ------------------
-- `owner_as_client = true` znamená, že chat majiteľa (`owner_chat_id`) sa
-- userbotu javí ako obyčajný fanúšik: modelka mu odpisuje rovnako ako komukoľvek
-- inému (`userbot.py:198` a `:319`). To je jediný spôsob, ako si klient vyskúša
-- jej povahu naživo, a je to zároveň jediný chat, ktorý sa smie vymazať —
-- `control_bot.py::_wipe` mazanie tvrdo obmedzuje na `owner_chat_id`.
--
-- PREČO MIGRÁCIA
-- --------------
-- Stĺpec pridala 006, ale 007 mu nedala update grant: `grant update (name,
-- tg_api_id, owner_chat_id, updated_at)`. Klient ho teda vidí (select grant má),
-- ale prepnúť ho vedel len ten, kto má service kľúč — čiže nikto z dashboardu.
-- Do dneška sa nastavoval ručne v SQL a v UI o ňom nebolo ani slovo.
--
-- PREČO REVOKE-THEN-GRANT
-- -----------------------
-- `grant update (col)` je v Postgrese prírastkový, takže by stačilo pridať jeden
-- stĺpec. Lenže potom by zoznam povolených stĺpcov nebol nikde vidieť celý a pri
-- ďalšej migrácii by sa nedalo prečítať, čo klient vlastne smie meniť. Revoke a
-- kompletný grant robí zo zoznamu jedno miesto pravdy — a zároveň to opraví
-- prípadné právo, ktoré by sem prisypali Supabase default privileges.
--
-- ČO SA VEDOME NEPRIDÁVA: `status`/`status_reason` (menia sa len cez
-- `set_model_status`), `model_type` (po založení sa nemení), `account_id`
-- (vlastníctvo), `claimed_by`/`heartbeat_at` (lease patrí workeru) a všetky
-- `*_enc` tajomstvá (tie von ani dnu nechodia inak než service kľúčom).
--
-- RLS sa nemení: `models_owner_update` zo 007 už drží „len vlastná modelka"
-- v `using` aj v `with check`.

-- ---------------------------------------------------------------------------
-- (a) Update grant — celý zoznam naraz
-- ---------------------------------------------------------------------------

revoke update on models from anon, authenticated;
grant update (name, tg_api_id, owner_chat_id, owner_as_client, updated_at)
  on models to authenticated;

-- ---------------------------------------------------------------------------
-- (b) Poistky — čo unikne, musí byť chyba migrácie
-- ---------------------------------------------------------------------------

do $$
declare
  v_secret text;
  v_probe uuid;
  v_account uuid;
  v_before boolean;
  v_after boolean;
  v_flipped boolean := false;
  v_reached boolean := false;
begin
  -- (1) To, kvôli čomu je táto migrácia.
  if not has_column_privilege('authenticated', 'public.models', 'owner_as_client', 'UPDATE') then
    raise exception 'owner_as_client stále nemá update grant';
  end if;

  -- (2) Stĺpce, ktoré klient meniť NESMIE. Zoznam je zámerne dlhší než to, čo
  --     táto migrácia rieši — revoke zhodil VŠETKY update granty a keby sa
  --     nasledujúci grant preklepol, tichým výsledkom by bolo priveľa práv.
  foreach v_secret in array array[
    'account_id', 'model_type', 'status', 'status_reason',
    'claimed_by', 'claimed_until', 'heartbeat_at',
    'tg_api_hash', 'tg_session_enc', 'control_bot_token_enc'
  ] loop
    if not exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = 'models' and column_name = v_secret
    ) then
      continue;  -- stĺpec v tejto verzii schémy neexistuje, nie je čo strážiť
    end if;
    if has_column_privilege('authenticated', 'public.models', v_secret, 'UPDATE')
       or has_column_privilege('anon', 'public.models', v_secret, 'UPDATE') then
      raise exception 'models.% je pre klienta zapisovateľný', v_secret;
    end if;
  end loop;

  -- (3) Klient, ktorý nie je prihlásený, nesmie na `models` vôbec nič.
  if has_table_privilege('anon', 'public.models', 'UPDATE') then
    raise exception 'anon má update na models';
  end if;

  -- (4) Živá skúška: prihlásený majiteľ svojej modelke prepínač naozaj prepne.
  --     Grant sám o sebe nestačí — RLS policy musí pustiť aj `with check`.
  --     Sonda beží na EXISTUJÚCEJ modelke (prednostne draft) a všetko, čo
  --     zmení, sa zahodí: vnútorný `begin ... exception` je implicitný
  --     savepoint, takže sentinel výnimka vráti aj hodnotu aj `set local role`.
  --     Produkčné riadky (Simona, Mio, Ayko Kuro) tak ostávajú nedotknuté —
  --     zmena sa nikdy nezacommituje a iná session ju ani neuvidí.
  select m.id, m.account_id, m.owner_as_client
    into v_probe, v_account, v_before
  from models m
  order by (m.status <> 'draft'), m.created_at
  limit 1;

  if v_probe is null then
    raise notice 'owner_as_client sonda preskočená — v models nie je ani jeden riadok';
  else
    begin
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_account, 'role', 'authenticated')::text,
                         true);
      set local role authenticated;

      update models set owner_as_client = not v_before, updated_at = now()
      where id = v_probe;

      select owner_as_client into v_after from models where id = v_probe;
      v_flipped := v_after is distinct from v_before;

      v_reached := true;
      raise exception 'owner-as-client-sonda-rollback' using errcode = 'P0001';
    exception when others then
      -- Sem sa ide sentinelom (hotovo, zahoď) alebo pádom updatu (chýbajúci
      -- grant → `insufficient_privilege`). V oboch prípadoch je sonda
      -- odrolovaná vrátane roly aj JWT; rozdiel medzi nimi podrží `v_reached`.
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then
      raise exception 'owner_as_client sonda spadla skôr, než dobehla — grant alebo RLS nepustili update';
    end if;
    if not v_flipped then
      raise exception 'owner_as_client sa majiteľovi nezmenil';
    end if;
    if (select owner_as_client from models where id = v_probe) is distinct from v_before then
      raise exception 'sonda po sebe nechala zmenenú modelku %', v_probe;
    end if;
  end if;
end $$;

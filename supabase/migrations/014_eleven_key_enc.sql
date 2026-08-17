-- Fáza 4 — ElevenLabs: vlastný kľúč klienta, šifrovaný.
--
-- DOTERAZ: `behavior.eleven_key` je čistý text, ktorý tam dostal len migračný
-- skript (Simona) alebo ručný SQL zásah. Klient ho v dashboarde nastaviť nevie
-- a ani nemá ako — 007 mu na tom stĺpci zámerne nedal žiadny column grant
-- (`select`/`insert`/`update` sú vymenované po stĺpcoch a `eleven_key` v nich
-- chýba), 010 to potvrdilo pri dorovnávaní driftu.
--
-- TERAZ: klient si má vedieť pripojiť SVOJ účet ElevenLabs a vybrať hlas. Kľúč
-- je cudzí API kredit — do prehliadača nepatrí ani majiteľovi, presne ako
-- Fanvue tokeny (011). Preto ide tou istou cestou:
--
--   web (server action, ENCRYPTION_KEY)  --encrypt-->  set_eleven_key(...)
--   worker (TenantDb, ENCRYPTION_KEY)    <--decrypt--  behavior.eleven_key_enc
--
-- Formát šifry je zhodný s `models.tg_session_enc` a `fanvue.access_token_enc`:
-- AES-256-GCM, `base64(nonce):base64(ct):base64(tag)` (`web/lib/crypto.ts` ↔
-- `worker/src/crypto.py`).
--
-- PREČO `eleven_key` NEZANIKÁ: Simone kľúč práve teraz funguje a beží z neho
-- produkcia. Backfill (`scripts/backfill_eleven_key.py`) doplní šifrovaný
-- dvojník, worker číta `_enc` prednostne a na starý stĺpec padá len keď je
-- `_enc` prázdny. Starý stĺpec sa vymaže až samostatnou migráciou, keď bude
-- UI vonku a `_enc` naplnený u všetkých.
--
-- POZOR na Supabase default privileges (lekcia z 007 a 011): nový STĹPEC na
-- existujúcej tabuľke zdedí právo, ktoré má tabuľka ako celok. `behavior` má
-- table-level grant iba na `delete`, takže by `eleven_key_enc` mal ostať
-- nedostupný — ale spoliehať sa na to je presne ten typ predpokladu, ktorý
-- raz tichým únikom API kľúča skončí. Preto sa nižšie explicitne odoberá
-- a v migrácii aj v reporte sa to overuje cez `has_column_privilege`.

-- ---------------------------------------------------------------------------
-- (a) Stĺpec
-- ---------------------------------------------------------------------------

alter table behavior
  add column if not exists eleven_key_enc text not null default '';

comment on column behavior.eleven_key_enc is
  'ElevenLabs API kľúč, AES-256-GCM (nonce:ct:tag). Zapisuje sa výhradne cez '
  'set_eleven_key(); číta ho len service_role (worker). Prázdne = kľúč nie je.';

comment on column behavior.eleven_key is
  'ZASTARANÉ — čistý text z čias jednomodelkovej inštalácie. Číta sa len ako '
  'fallback, kým nie je naplnený eleven_key_enc. Zmizne samostatnou migráciou.';

-- ---------------------------------------------------------------------------
-- (b) Granty — ani jeden z tých dvoch stĺpcov klient nevidí a nezapíše
-- ---------------------------------------------------------------------------
--
-- `revoke` na stĺpec bez ACL záznamu je no-op (Postgres nanajvýš varuje), takže
-- toto je bezpečné spustiť aj opakovane. Ide o poistku, nie o opravu.

revoke select (eleven_key_enc), insert (eleven_key_enc), update (eleven_key_enc)
  on behavior from authenticated, anon;
revoke select (eleven_key), insert (eleven_key), update (eleven_key)
  on behavior from authenticated, anon;

-- Poistka sa musí sama skontrolovať, inak je to len komentár.
do $$
declare col text;
begin
  foreach col in array array['eleven_key', 'eleven_key_enc'] loop
    if has_column_privilege('authenticated', 'public.behavior', col, 'SELECT')
       or has_column_privilege('authenticated', 'public.behavior', col, 'UPDATE')
       or has_column_privilege('authenticated', 'public.behavior', col, 'INSERT')
       or has_column_privilege('anon', 'public.behavior', col, 'SELECT') then
      raise exception 'behavior.% je pre klienta dostupný — grant unikol', col;
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- (c) set_eleven_key — jediná cesta, ktorou kľúč do DB vojde
-- ---------------------------------------------------------------------------
--
-- Volá ju server action po tom, čo kľúč zašifrovala. `security definer`, lebo
-- `authenticated` na stĺpec právo nemá a mať nesmie; vlastníctvo modelky si
-- funkcia overí sama — `grant execute ... to authenticated` znamená, že ju
-- vie zavolať KTOKOĽVEK prihlásený, aj s cudzím `p_model`.

create or replace function set_eleven_key(p_model uuid, p_key_enc text)
returns void language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_enc text := coalesce(p_key_enc, '');
begin
  if not exists (
    select 1 from models m where m.id = p_model and m.account_id = (select auth.uid())
  ) then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  if v_enc = '' then
    raise exception 'eleven key required';
  end if;

  -- Tvar šifry (nonce:ct:tag v base64). Nechráni to pred zlým kľúčom, ale pred
  -- tým, čo sa stane oveľa pravdepodobnejšie: server action zabudne zašifrovať
  -- a do DB pošle holý `sk_…`. Taký zápis tu skončí chybou, nie tichým únikom.
  if v_enc !~ '^[A-Za-z0-9+/]+={0,2}:[A-Za-z0-9+/]+={0,2}:[A-Za-z0-9+/]+={0,2}$' then
    raise exception 'eleven key must be encrypted (nonce:ct:tag)';
  end if;

  update behavior
     set eleven_key_enc = v_enc,
         -- Starý čistý text prestáva platiť v tej istej sekunde, ako príde nový
         -- kľúč — dva zdroje pravdy by znamenali, že sa raz použije ten zlý.
         eleven_key = '',
         updated_at = now()
   where model_id = p_model;

  if not found then
    raise exception 'behavior row missing for model %', p_model;
  end if;
end;
$$;

revoke execute on function set_eleven_key(uuid, text) from public, anon;
grant execute on function set_eleven_key(uuid, text) to authenticated;

-- ---------------------------------------------------------------------------
-- (d) clear_eleven_key — odpojenie účtu
-- ---------------------------------------------------------------------------

create or replace function clear_eleven_key(p_model uuid)
returns void language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if not exists (
    select 1 from models m where m.id = p_model and m.account_id = (select auth.uid())
  ) then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  -- Oba stĺpce naraz: odpojiť účet a nechať v DB starý čistý text by bolo to
  -- najhoršie z oboch svetov — klient si myslí, že kľúč zmazal, a worker ho
  -- cez fallback ďalej používa.
  update behavior
     set eleven_key_enc = '', eleven_key = '', updated_at = now()
   where model_id = p_model;

  if not found then
    raise exception 'behavior row missing for model %', p_model;
  end if;
end;
$$;

revoke execute on function clear_eleven_key(uuid) from public, anon;
grant execute on function clear_eleven_key(uuid) to authenticated;

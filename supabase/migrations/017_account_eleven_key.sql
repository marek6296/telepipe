-- ElevenLabs kľúč patrí ÚČTU, nie modelke.
--
-- DOTERAZ (014): `behavior.eleven_key_enc` — jeden kľúč na modelku. Vyzeralo to
-- správne, kým mal každý jednu; Marek má dve (Simona, Mio) a v oboch riadkoch
-- je BITOVO ten istý kľúč (overené sha256 čistého textu). Kto si založí piatu
-- modelku, lepil by ten istý `sk_…` päťkrát a pri prekľúčovaní ho päťkrát
-- hľadal. Účet ElevenLabs je jeden, fakturácia je jedna — kľúč je vlastnosť
-- účtu telepipe, nie modelky.
--
-- TERAZ: `accounts.eleven_key_enc`. Pripojenie sa robí RAZ v nastaveniach účtu,
-- na karte modelky sa vyberá už len hlas (`behavior.eleven_voice_id`, na ten
-- klient grant má od 007).
--
-- Cesta kľúča sa nemení, len sa posúva o úroveň vyššie:
--
--   web (server action, ENCRYPTION_KEY) --encrypt--> set_account_eleven_key(...)
--   worker (AccountKeyCache, ENCRYPTION_KEY) <--decrypt-- accounts.eleven_key_enc
--
-- Formát šifry je zhodný so všetkým ostatným (`models.tg_session_enc`,
-- `fanvue.access_token_enc`, `behavior.eleven_key_enc`): AES-256-GCM,
-- `base64(nonce):base64(ct):base64(tag)` — `web/lib/crypto.ts` ↔
-- `worker/src/crypto.py`.
--
-- ČO SA NERUŠÍ
-- ------------
-- `behavior.eleven_key_enc` ani `behavior.eleven_key` táto migrácia NEMAŽE a
-- staré RPC (`set_eleven_key`, `clear_eleven_key`, `has_eleven_key`) necháva
-- žiť nedotknuté. Dôvod je rollback: keby sa nasadenie muselo vrátiť, starý
-- worker aj starý web musia nájsť svet taký, aký ho nechali. Web ich prestáva
-- volať (nikdy ich reálne ani nevolal — sekcia bola „Coming soon"), worker číta
-- účet prednostne a na model padá len keď účet kľúč nemá. Zmiznú samostatnou
-- migráciou, keď bude `accounts.eleven_key_enc` naplnený u všetkých a nasadené
-- to pobeží týždeň.

-- ---------------------------------------------------------------------------
-- (a) Stĺpec
-- ---------------------------------------------------------------------------

alter table accounts
  add column if not exists eleven_key_enc text not null default '';

comment on column accounts.eleven_key_enc is
  'ElevenLabs API kľúč účtu, AES-256-GCM (nonce:ct:tag). Zapisuje sa výhradne '
  'cez set_account_eleven_key(); číta ho len service_role (worker + server '
  'actions). Prázdne = účet nie je pripojený. Platí pre VŠETKY modelky účtu.';

-- ---------------------------------------------------------------------------
-- (b) Granty — a prečo tu samotný `revoke` na stĺpec NESTAČÍ
-- ---------------------------------------------------------------------------
--
-- Pri `behavior` (014) stačilo stĺpec odobrať, lebo tá tabuľka má table-level
-- grant iba na `delete` — `select/insert/update` sú tam vymenované po stĺpcoch.
--
-- `accounts` je iná: 007 dala `grant select on accounts to authenticated`, teda
-- grant na CELÚ tabuľku. A Postgres hovorí jasne (REVOKE, Notes):
--
--     „if a role has been granted privileges on a table, then revoking the
--      same privileges from individual columns will have no effect."
--
-- Column-level `revoke` by tu bol teda tichý no-op a `eleven_key_enc` by si
-- prihlásený používateľ vytiahol obyčajným `select eleven_key_enc from accounts`
-- — vlastný riadok mu policy `accounts_owner_select` pustí. Preto sa table-level
-- grant RUŠÍ a nahrádza vymenovaním stĺpcov.
--
-- Vedľajší (a vítaný) účinok: každý ďalší stĺpec na `accounts` je odteraz pre
-- klienta neviditeľný, kým ho niekto vedome nedopíše do zoznamu nižšie. Presne
-- opačne než doteraz — a presne to je pri tabuľke, kde bývajú tajomstvá, tá
-- správna strana omylu.
--
-- 009 a 013 pridali `grant select (role, plan)` a `grant select (unlimited)`;
-- tie boli popri table-level grante nadbytočné, teraz sú jediné, čo tie stĺpce
-- drží čitateľné. Kvôli čitateľnosti sú aj tak všetky v jednom zozname.

revoke select on accounts from authenticated, anon;

grant select (id, email, credit_balance_usd, created_at, role, plan, unlimited)
  on accounts to authenticated;

-- Poistka nad poistkou: keby niekto v budúcnosti table-level grant vrátil,
-- toto ho na tomto stĺpci aspoň neprežije bez povšimnutia (self-check nižšie).
revoke select (eleven_key_enc), insert (eleven_key_enc), update (eleven_key_enc)
  on accounts from authenticated, anon;

-- Poistka sa musí sama skontrolovať, inak je to len komentár.
do $$
begin
  -- 1. tajomstvo nesmie byť vidieť ani prepísať
  if has_column_privilege('authenticated', 'public.accounts', 'eleven_key_enc', 'SELECT')
     or has_column_privilege('authenticated', 'public.accounts', 'eleven_key_enc', 'UPDATE')
     or has_column_privilege('authenticated', 'public.accounts', 'eleven_key_enc', 'INSERT')
     or has_column_privilege('anon', 'public.accounts', 'eleven_key_enc', 'SELECT') then
    raise exception 'accounts.eleven_key_enc je pre klienta dostupný — grant unikol';
  end if;

  -- 2. a zvyšok riadku musí ostať čitateľný, inak sme práve rozbili /app/account
  if not (
    has_column_privilege('authenticated', 'public.accounts', 'id', 'SELECT')
    and has_column_privilege('authenticated', 'public.accounts', 'email', 'SELECT')
    and has_column_privilege('authenticated', 'public.accounts', 'credit_balance_usd', 'SELECT')
    and has_column_privilege('authenticated', 'public.accounts', 'created_at', 'SELECT')
    and has_column_privilege('authenticated', 'public.accounts', 'role', 'SELECT')
    and has_column_privilege('authenticated', 'public.accounts', 'plan', 'SELECT')
    and has_column_privilege('authenticated', 'public.accounts', 'unlimited', 'SELECT')
  ) then
    raise exception 'accounts: klient stratil čítanie vlastného riadku';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- (c) set_account_eleven_key — jediná cesta, ktorou kľúč do DB vojde
-- ---------------------------------------------------------------------------
--
-- Žiadny `p_account` parameter, a to zámerne: 014 musela `p_model` prijať a
-- vlastníctvo si overiť, lebo modeliek je veľa. Účet je práve jeden — ten
-- prihlásený. Keď ho funkcia berie z `auth.uid()`, cudzí účet sa nedá zasiahnuť
-- ani preklepom, ani útokom; nie je čo overovať, lebo nie je čo podvrhnúť.

create or replace function set_account_eleven_key(p_key_enc text)
returns void language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_enc text := coalesce(p_key_enc, '');
  v_id  uuid := (select auth.uid());
begin
  if v_id is null then
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

  update accounts set eleven_key_enc = v_enc where id = v_id;

  if not found then
    raise exception 'account row missing for %', v_id;
  end if;
end;
$$;

revoke execute on function set_account_eleven_key(text) from public, anon;
grant execute on function set_account_eleven_key(text) to authenticated;

-- ---------------------------------------------------------------------------
-- (d) clear_account_eleven_key — odpojenie účtu
-- ---------------------------------------------------------------------------
--
-- Maže sa LEN stĺpec na účte. Prípadné staré `behavior.eleven_key*` sa
-- nedotýkame: sú to iné dáta, na iné migračné hodiny, a odpojenie účtu nesmie
-- byť príležitosť ticho zmazať niečo, o čom tlačidlo v UI nehovorí. (Worker
-- však po odpojení účtu na model FALLBACKNE — je to zdokumentované v `db.py`
-- a je to zámer: kým existuje per-model kľúč, je platný.)

create or replace function clear_account_eleven_key()
returns void language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_id uuid := (select auth.uid());
begin
  if v_id is null then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  update accounts set eleven_key_enc = '' where id = v_id;

  if not found then
    raise exception 'account row missing for %', v_id;
  end if;
end;
$$;

revoke execute on function clear_account_eleven_key() from public, anon;
grant execute on function clear_account_eleven_key() to authenticated;

-- ---------------------------------------------------------------------------
-- (e) has_account_eleven_key — „mám pripojené?" bez toho, aby kľúč opustil DB
-- ---------------------------------------------------------------------------
--
-- Von ide jediný bit. Zámerne pozerá LEN na `accounts.eleven_key_enc` a nie aj
-- na modelky: toto je stav TLAČIDLA v nastaveniach účtu. Keby sa doň počítal
-- zdedený per-model kľúč, „Disconnect" by nechal kartu naďalej svietiť
-- „Connected" a používateľ by správne usúdil, že tlačidlo nefunguje.

create or replace function has_account_eleven_key()
returns boolean language plpgsql stable security definer
set search_path = public, pg_temp as $$
declare v_has boolean;
begin
  select a.eleven_key_enc <> '' into v_has
  from accounts a where a.id = (select auth.uid());

  return coalesce(v_has, false);
end;
$$;

revoke execute on function has_account_eleven_key() from public, anon;
grant execute on function has_account_eleven_key() to authenticated;

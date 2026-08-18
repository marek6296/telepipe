-- Párovanie kontrolného bota kódom namiesto ručne opísaného chat id.
--
-- PREČO. `owner_chat_id` bolo doteraz číslo, ktoré si klient musel odniekiaľ
-- opísať (@userinfobot) a vlepiť do dashboardu. Preklep sa nedal odhaliť:
-- `control_bot.py` gatuje KAŽDÝ handler na `chat_id == cfg.owner_chat_id`,
-- takže pri zlom čísle bot mlčí aj na `/start`. Namiesto toho si dashboard
-- vypýta jednorazový kód, klient ho pošle svojmu botovi a bot si chat id
-- zapíše sám — z toho chatu, ktorý kód naozaj poslal.
--
-- BEZPEČNOSŤ. Kód je jediná vec, ktorú bot prijme od neznámeho chatu, takže
-- musí platiť:
--   * kód generuje SERVER (default + before-insert trigger), nie klient —
--     inak by si útočník zvolil kód, ktorý pošle obeti;
--   * platí 15 minút a práve raz (`used_at`);
--   * naraz žije nanajvýš jeden na modelku (partial unique index);
--   * hľadá sa VŽDY v páre s `model_id`, takže kód jednej modelky nespáruje
--     inú (kolízie kódov naprieč modelkami sú preto neškodné).
--
-- GRANTY. Rovnaké pravidlo ako v 007: Supabase má nastavené `alter default
-- privileges ... grant all on tables to anon, authenticated`, takže nová
-- tabuľka dostane pri vzniku plné práva. Najprv sa preto všetko odoberie a
-- potom sa pridá len to, čo klient naozaj potrebuje.

-- ---------------------------------------------------------------------------
-- (a) Generátor kódu
-- ---------------------------------------------------------------------------

-- Abeceda bez znakov, ktoré si klient pri prepisovaní pomýli: chýba 0/O a 1/I.
-- Zvyšných 32 znakov delí 256 bezo zvyšku, takže `get_byte(...) % 32` nemá
-- modulo bias — na rozdiel od `random()` je to aj kryptograficky náhodné
-- (pgcrypto je zapnuté v 001).
--
-- `extensions` v search_path je nutné: v hostovanom Supabase žije pgcrypto
-- práve tam, nie v `public` (`create extension if not exists` z 001 je na
-- takom projekte no-op). Pri lokálnej DB, kde je v `public`, sa to vyrieši
-- rovnako — `public` je v ceste prvé.
create or replace function gen_pairing_code()
returns text language plpgsql
set search_path = public, extensions, pg_temp as $$
declare
  alphabet constant text := '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
  bytes bytea := gen_random_bytes(6);
  out text := '';
  i int;
begin
  for i in 0..5 loop
    out := out || substr(alphabet, (get_byte(bytes, i) % 32) + 1, 1);
  end loop;
  return 'TP-' || out;
end;
$$;

revoke execute on function gen_pairing_code() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- (b) Tabuľka
-- ---------------------------------------------------------------------------

create table control_bot_links (
  id bigint generated always as identity primary key,
  model_id uuid not null references models(id) on delete cascade,
  account_id uuid not null references accounts(id) on delete cascade,
  -- Zámerne BEZ `default gen_pairing_code()`: default sa vyhodnocuje právami
  -- toho, kto vkladá, takže by klientovi hodil „permission denied for function
  -- gen_pairing_code". Kód dopĺňa before-insert trigger nižšie (security
  -- definer) — generátor tak ostáva klientovi úplne nedostupný. `not null` sa
  -- kontroluje až po triggeri, takže insert bez kódu prejde.
  code text not null,
  -- Chat, ktorý kód poslal. Zapisuje ho worker (service key) spolu s `used_at`.
  paired_chat_id bigint,
  used_at timestamptz,
  expires_at timestamptz not null default now() + interval '15 minutes',
  created_at timestamptz not null default now()
);

-- Kód si nezvolí ani ten, kto by na stĺpec grant mal. `security definer` je
-- tu nutné: generátor je pre `authenticated` nedostupný a trigger ho volá
-- v jeho mene.
create or replace function force_pairing_code()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  new.code := gen_pairing_code();
  return new;
end;
$$;

revoke execute on function force_pairing_code() from public, anon, authenticated;

create trigger control_bot_links_code
  before insert on control_bot_links
  for each row execute function force_pairing_code();

-- Naraz žije nanajvýš jeden nepoužitý kód na modelku. `expires_at > now()` sa
-- do predikátu indexu dať NEDÁ (musel by byť IMMUTABLE), takže slot uvoľní až
-- použitie alebo zmazanie — dashboard preto pred generovaním nový kód staré
-- nepoužité riadky maže (má na to delete policy nižšie).
create unique index control_bot_links_live_idx
  on control_bot_links (model_id) where used_at is null;
-- Worker hľadá výhradne dvojicou (model_id, code).
create index control_bot_links_lookup_idx on control_bot_links (model_id, code);
create index control_bot_links_account_idx on control_bot_links (account_id);

-- ---------------------------------------------------------------------------
-- (c) RLS + granty
-- ---------------------------------------------------------------------------

alter table control_bot_links enable row level security;

revoke all on control_bot_links from anon, authenticated;

create policy control_bot_links_owner_select on control_bot_links
  for select to authenticated
  using (account_id = (select auth.uid())
         and model_id in (select id from models where account_id = (select auth.uid())));

create policy control_bot_links_owner_insert on control_bot_links
  for insert to authenticated
  with check (account_id = (select auth.uid())
              and model_id in (select id from models where account_id = (select auth.uid())));

-- Mazať sa smú len nepoužité kódy — spárovaný riadok je záznam o tom, ktorý
-- chat sa kedy pripojil, a ten klient prepisovať nemá.
create policy control_bot_links_owner_delete on control_bot_links
  for delete to authenticated
  using (used_at is null
         and account_id = (select auth.uid())
         and model_id in (select id from models where account_id = (select auth.uid())));

grant select (id, model_id, code, used_at, expires_at, paired_chat_id)
  on control_bot_links to authenticated;
-- `code`, `used_at`, `paired_chat_id` ani `expires_at` klient nezapisuje:
-- kód generuje server, zvyšok plní worker.
grant insert (model_id, account_id) on control_bot_links to authenticated;
grant delete on control_bot_links to authenticated;

-- ---------------------------------------------------------------------------
-- (d) Spotrebovanie kódu — jedna transakcia, jeden RPC pre workera
-- ---------------------------------------------------------------------------

-- Prečo RPC a nie dva PostgREST dotazy: medzi „označ kód za použitý" a „zapíš
-- owner_chat_id" nesmie byť okno, v ktorom je kód minutý a majiteľ nenastavený
-- — klient by ostal bez ovládania a s kódom, ktorý už druhýkrát nezaberie.
-- `update ... returning` zároveň rieši súbeh: dva chaty s tým istým kódom
-- v tej istej sekunde prejdú serializovane a druhý dostane `false`.
create or replace function pair_control_bot(p_model uuid, p_code text, p_chat bigint)
returns boolean language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_id bigint;
begin
  if p_chat is null or p_chat = 0 then
    return false;
  end if;

  update control_bot_links
     set used_at = now(), paired_chat_id = p_chat
   where model_id = p_model
     and code = upper(btrim(p_code))
     and used_at is null
     and expires_at > now()
  returning id into v_id;

  if v_id is null then
    return false;
  end if;

  update models
     set owner_chat_id = p_chat, updated_at = now()
   where id = p_model;

  return true;
end;
$$;

revoke execute on function pair_control_bot(uuid, text, bigint)
  from public, anon, authenticated;
grant execute on function pair_control_bot(uuid, text, bigint) to service_role;

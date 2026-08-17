-- Typ agenta: `models.model_type`.
--
-- DOTERAZ: každá „modelka" bola to isté — persona, hlasovky, funnel, Fanvue.
-- Celý produkt sedel na jednom nevyslovenom predpoklade, že klient chce AI
-- dievča. Prvý klient, ktorý bude chcieť firemného agenta, ten predpoklad
-- rozbije: iná persona, iné nastavenia, iný beh — a Fanvue, ktoré firma nikdy
-- mať nebude.
--
-- TERAZ: typ je stĺpec na modelke a rozhoduje sa PRI ZALOŽENÍ. Nemení sa —
-- klient naň nemá update grant a `models_type_guard` mu ho ustráži aj keby ho
-- dostal. Prepnúť dievča na firmu by znamenalo nechať za sebou personu, hlas a
-- Fanvue token, ktoré k novému typu nepatria; kto chce iný typ, založí si ho.
--
-- ČO TÁTO MIGRÁCIA ZÁMERNE NEROBÍ
-- --------------------------------
-- Nezakladá `business`/`private` beh. Typy existujú v `check` (aby ich neskorší
-- kód nemusel meniť tvar tabuľky), ale založiť sa dnes dá LEN `persona`. Stráži to
-- `model_type_enabled()` — jediné miesto, kde je zoznam povolených typov, a
-- jediný riadok, ktorý bude treba zmeniť, keď firemný agent naozaj pobeží.
--
-- Backfill je implicitný cez `default 'persona'`: Simona aj Mio bežia dnes ako
-- persona agenti a po tejto migrácii bežia ďalej rovnako. Žiadny UPDATE na
-- produkčné riadky sa tu nerobí.
--
-- POZN. K HISTÓRII: v produkcii sa 018 aplikovala ešte s hodnotou `girl`;
-- premenovanie na neutrálne `persona` doviedla `018b_model_type_persona.sql`.
-- Tento súbor je cieľový stav — čistá DB si ho prehrá rovno takto a 018b na nej
-- neurobí nič.

-- ---------------------------------------------------------------------------
-- (a) Stĺpec
-- ---------------------------------------------------------------------------

alter table models
  add column if not exists model_type text not null default 'persona';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'models_type_valid'
  ) then
    alter table models
      add constraint models_type_valid
      check (model_type in ('persona','business','private'));
  end if;
end $$;

comment on column models.model_type is
  'Typ agenta: persona (persona/hlas/funnel/Fanvue), business, private. Volí sa '
  'pri založení a nemení sa. Dnes je založiteľný len persona — viď '
  'model_type_enabled() a trigger models_type_guard.';

-- `claim_models` po novom filtruje aj podľa typu; bez indexu by z toho bol
-- seq scan pri každom ticku každej repliky.
drop index if exists models_claim_idx;
create index if not exists models_claim_idx
  on models (status, model_type, claimed_by, heartbeat_at);

-- ---------------------------------------------------------------------------
-- (b) „Coming soon" — jediný zoznam povolených typov
-- ---------------------------------------------------------------------------
--
-- Prečo funkcia a nie `check (model_type = 'persona')`: check by sa musel pri
-- spustení firemného agenta zahodiť a nahradiť, čo je zámena obmedzenia za iné
-- obmedzenie na tabuľke s produkčnými dátami. Funkciu stačí prepísať jedným
-- `create or replace` a nič sa nezamyká.
--
-- Prečo vôbec: server action síce typ validuje proti allowlistu, ale UI nie je
-- hranica bezpečnosti. Kto pošle `model_type: 'business'` priamo do PostgREST
-- (grant na insert ten stĺpec má, viď (c)), musí naraziť tu.

create or replace function model_type_enabled(p_type text)
returns boolean language sql immutable
set search_path = public, pg_temp as $$
  -- Rozšíriť, až keď pre daný typ existuje beh vo workeri aj UI.
  select p_type = 'persona';
$$;

revoke execute on function model_type_enabled(text) from public, anon;
grant execute on function model_type_enabled(text) to authenticated;

create or replace function models_type_guard()
returns trigger language plpgsql
set search_path = public, pg_temp as $$
begin
  if tg_op = 'UPDATE' and new.model_type is not distinct from old.model_type then
    return new;
  end if;

  if not model_type_enabled(new.model_type) then
    raise exception 'model type not available yet'
      using errcode = '22023',
            detail = format('model_type=%L', new.model_type);
  end if;

  return new;
end;
$$;

revoke execute on function models_type_guard() from public, anon, authenticated;

drop trigger if exists models_type_guard on models;
create trigger models_type_guard
  before insert or update of model_type on models
  for each row execute function models_type_guard();

-- ---------------------------------------------------------------------------
-- (c) Granty
-- ---------------------------------------------------------------------------
--
-- `models` má od 007 column-scoped `select` aj `insert` — nový stĺpec je teda
-- pre klienta neviditeľný aj nezapísateľný, kým sa sem vedome nedopíše. To je
-- správna strana omylu, ale pre `model_type` chceme oboje:
--
--   select — UI podľa neho skladá taby (Fanvue má len `persona`) a štítok na karte,
--   insert — typ sa volí pri založení, inak by bol každý model navždy `persona`.
--
-- `update` sa NEDÁVA: typ sa nemení (viď hlavička). Guard z (b) je poistka pre
-- prípad, že by ho niekto v budúcnosti pridal.
--
-- Granty sú čisto prírastkové — 007 dala `insert (account_id, name)` po
-- stĺpcoch a table-level `revoke insert` by ich vzal so sebou. Pridáva sa teda
-- len chýbajúci stĺpec a self-check overí, že zvyšok prežil.

grant select (model_type) on models to authenticated;
grant insert (model_type) on models to authenticated;

do $$
begin
  if not has_column_privilege('authenticated', 'public.models', 'model_type', 'SELECT')
     or not has_column_privilege('authenticated', 'public.models', 'model_type', 'INSERT') then
    raise exception 'models.model_type: klient ho nevie prečítať alebo zapísať';
  end if;

  -- „Add model" potrebuje všetky tri stĺpce naraz.
  if not (
    has_column_privilege('authenticated', 'public.models', 'account_id', 'INSERT')
    and has_column_privilege('authenticated', 'public.models', 'name', 'INSERT')
  ) then
    raise exception 'models: klient stratil insert na account_id/name';
  end if;

  -- Typ sa nemení ani majiteľovi.
  if has_column_privilege('authenticated', 'public.models', 'model_type', 'UPDATE') then
    raise exception 'models.model_type: update grant unikol — typ sa nemá dať meniť';
  end if;

  -- A tajomstvá musia ostať tajomstvami aj po zásahu do grantov.
  if has_column_privilege('authenticated', 'public.models', 'tg_session_enc', 'SELECT')
     or has_column_privilege('authenticated', 'public.models', 'control_bot_token_enc', 'SELECT') then
    raise exception 'models: šifrované stĺpce sa stali čitateľnými';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- (d) claim_models — worker si berie len to, čo vie obslúžiť
-- ---------------------------------------------------------------------------
--
-- Toto je bezpečnostná poistka, nie optimalizácia. Riadok s typom, pre ktorý
-- ešte neexistuje beh, nesmie skončiť v `TenantRunner` — spustila by sa na ňom
-- Telethon session a dievčenský agent by odpisoval firemným zákazníkom.
--
-- Keď pribudne firemný runner, dostane vlastné napojenie (buď parameter
-- `p_types` do tejto RPC, alebo vlastná claim funkcia pre vlastnú flotilu
-- replík) — pool v `worker/src/main.py` je jeden na typ, nie jeden na všetko.
-- Dovtedy je zoznam tu, v jednom riadku.

create or replace function claim_models(p_replica text, p_capacity int)
returns setof models language sql security definer
set search_path = public, pg_temp as $$
  update models m set claimed_by = p_replica, heartbeat_at = now()
  where m.id in (
    select id from models
    where status = 'active'
      and model_type = 'persona'
      and (claimed_by is null or heartbeat_at < now() - interval '90 seconds')
      and (claimed_by is distinct from p_replica)
    order by created_at
    for update skip locked
    limit p_capacity
  )
  returning m.*;
$$;

-- 002 tieto práva už raz zrala; `create or replace` ACL zachováva, ale
-- opakovanie je lacnejšie než predpoklad.
revoke execute on function claim_models(text, int) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- (e) admin_list_models — typ do admin tabuľky
-- ---------------------------------------------------------------------------
--
-- `returns table` sa nedá rozšíriť cez `create or replace` (Postgres to odmietne
-- ako zmenu návratového typu), preto drop + create. Revoke/grant sa pri drope
-- stratia, takže sa dávajú nanovo.

drop function if exists admin_list_models();

create or replace function admin_list_models()
returns table (
  id uuid, account_id uuid, account_email text, name text,
  model_type text,
  status text, status_reason text, claimed_by text, heartbeat_at timestamptz,
  msgs_today bigint, spend_today numeric
)
language plpgsql stable security definer
set search_path = public, pg_temp as $$
#variable_conflict use_column
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;

  -- Zámerne LEN metadáta: obsah konverzácií klienta admin cez toto RPC nevidí.
  return query
  select m.id, m.account_id, a.email, m.name,
         m.model_type,
         m.status, m.status_reason, m.claimed_by, m.heartbeat_at,
         (select count(*) from dm_messages d
           where d.model_id = m.id and d.created_at >= date_trunc('day', now())),
         coalesce((select sum(u.charged_usd) from usage_events u
                    where u.model_id = m.id
                      and u.created_at >= date_trunc('day', now())), 0)
  from models m join accounts a on a.id = m.account_id
  order by a.email, m.created_at;
end;
$$;

revoke execute on function admin_list_models() from public, anon;
grant execute on function admin_list_models() to authenticated;

-- ---------------------------------------------------------------------------
-- (f) Self-check
-- ---------------------------------------------------------------------------

do $$
declare v_bad int;
begin
  -- Produkčné modelky musia byť dievčatá — inak by ich claim prestal brať a
  -- Simona s Miom by ticho zmĺkli.
  select count(*) into v_bad from models where model_type <> 'persona';
  if v_bad > 0 then
    raise exception 'existujúce modelky nie sú persona (%) — claim by ich prestal brať', v_bad;
  end if;

  if model_type_enabled('business') or model_type_enabled('private') then
    raise exception 'model_type_enabled pustil typ, ktorý ešte nemá beh';
  end if;
  if not model_type_enabled('persona') then
    raise exception 'model_type_enabled odmieta persona — nič by sa nedalo založiť';
  end if;
end $$;

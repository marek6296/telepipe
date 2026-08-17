-- Fáza 3.1 — Fanvue: pripojenie účtu (OAuth 2.0 + PKCE) a fronta webhookov.
--
-- Predloha: `simona-dashboard` mala jednu tabuľku `fanvue` v každej schéme
-- (jeden riadok, `id = 1`). V Telepipe je všetko v `public` a tenanta rozlišuje
-- `model_id` — preto je `model_id` rovno primárnym kľúčom (jeden Fanvue účet na
-- modelku, viac ich ani nedáva zmysel).
--
-- Tokeny sú šifrované rovnakým AES-256-GCM ako `models.tg_session_enc`
-- (`web/lib/crypto.ts` ↔ `worker/src/crypto.py`, formát nonce:ct:tag). Do
-- prehliadača nejdú NIKDY — ani majiteľovi; `authenticated` na `*_enc` stĺpce
-- nemá column grant a číta ich len service kľúč (server actions + worker).
--
-- POZOR na Supabase default privileges (lekcia z 007): v projekte je
-- `alter default privileges ... grant all on tables to anon, authenticated`,
-- takže KAŽDÁ nová tabuľka vznikne s plnými právami pre obe roly. Column-scoped
-- grant by na už existujúce plné právo nemal účinok — preto sa najprv všetko
-- odoberá (`revoke all`) a až potom pridáva to, čo klient naozaj potrebuje.

-- ---------------------------------------------------------------------------
-- (a) fanvue — jeden pripojený účet na modelku
-- ---------------------------------------------------------------------------

create table fanvue (
  model_id uuid primary key references models(id) on delete cascade,
  connected boolean not null default false,

  -- `enabled` je vypínač ODPISOVANIA, nie pripojenia. Portovaný agent
  -- (`worker/src/fanvue_agent.py`) ho číta ako `settings["enabled"]` — meno
  -- teda diktuje kód, nie my. Default `false` je zámerný: fáza 3.1 prináša len
  -- pripojenie a frontu; dátová vrstva agenta (fv_users/fv_messages/fv_media…)
  -- príde vo fáze 3.2. Kým je `false`, worker agenta ani nespustí a udalosti
  -- sa vo fronte kopia namiesto toho, aby ich prázdny agent zahodil.
  -- Klient ho prepnúť nevie — v grantoch nižšie zámerne nie je.
  enabled boolean not null default false,

  access_token_enc text not null default '',
  refresh_token_enc text not null default '',
  expires_at timestamptz,
  scope text not null default '',

  -- Identita na Fanvue. `creator_uuid` je zároveň smerovacia adresa webhookov:
  -- všetky modelky zdieľajú jeden endpoint a rozlíši ich až uuid v tele.
  creator_uuid text not null default '',
  handle text not null default '',
  display_name text not null default '',

  last_error text not null default '',
  updated_at timestamptz not null default now()
);

-- Jeden Fanvue účet nesmie byť pripojený k dvom modelkám — inak by webhook
-- nemal ako rozhodnúť, komu udalosť patrí. Prázdna hodnota (nepripojené)
-- je bežná, preto partial index.
create unique index fanvue_creator_idx on fanvue (creator_uuid)
  where creator_uuid <> '';

-- ---------------------------------------------------------------------------
-- (b) fanvue_events — fronta medzi webhookom (web) a agentom (worker)
-- ---------------------------------------------------------------------------
--
-- Webhook nesmie nič počítať: Fanvue čaká odpoveď ~10 s a pomalé spracovanie
-- pred odpoveďou vyrobí timeout, opakované doručenie a tým duplicitu. Uložené
-- = vybavené, zvyšok si vezme worker.

create table fanvue_events (
  id bigint generated always as identity primary key,
  model_id uuid not null references models(id) on delete cascade,
  -- `id` z tela udalosti. Fanvue doručenie opakuje, takže bez neho by tá istá
  -- správa prišla do fronty niekoľkokrát.
  event_id text not null default '',
  event_type text not null default '',
  payload jsonb not null default '{}'::jsonb,
  -- null = čaká na spracovanie. Agent si berie najstaršie nespracované.
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create unique index fanvue_events_dedup_idx on fanvue_events (model_id, event_id)
  where event_id <> '';
create index fanvue_events_pending_idx on fanvue_events (model_id, id)
  where processed_at is null;

-- ---------------------------------------------------------------------------
-- (c) Singleton riadok pri vzniku modelky
-- ---------------------------------------------------------------------------
--
-- Web aj worker riadok len PATCHujú a PATCH na neexistujúci riadok ticho nič
-- neurobí — preto ho zakladá ten istý trigger ako persona/behavior/settings.

create or replace function provision_model_rows()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  insert into persona  (model_id) values (new.id) on conflict do nothing;
  insert into behavior (model_id) values (new.id) on conflict do nothing;
  insert into settings (model_id) values (new.id) on conflict do nothing;
  insert into fanvue   (model_id) values (new.id) on conflict do nothing;
  return new;
end;
$$;

-- `create or replace` práva zachováva, ale radšej to zopakujeme — funkcia
-- nesmie byť volateľná cez /rest/v1/rpc (security advisor z 007).
revoke execute on function provision_model_rows() from public, anon, authenticated;

-- Modelky, ktoré vznikli pred touto migráciou, riadok ešte nemajú.
insert into fanvue (model_id)
select id from models
on conflict do nothing;

-- ---------------------------------------------------------------------------
-- (d) RLS + granty
-- ---------------------------------------------------------------------------

alter table fanvue enable row level security;
alter table fanvue_events enable row level security;

-- Nové tabuľky dostali default privileges (plné práva pre anon aj
-- authenticated) — zhodiť a dať len to potrebné.
revoke all on fanvue from anon, authenticated;
revoke all on fanvue_events from anon, authenticated;

-- Majiteľ vidí STAV pripojenia svojich modeliek. Zapisovať nesmie nič: všetko
-- ide cez server actions / route handlery so service kľúčom, ktoré si samy
-- overia vlastníctvo (`connect`, `disconnect`, callback OAuth).
create policy fanvue_owner_select on fanvue
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

-- `access_token_enc` / `refresh_token_enc` tu zámerne NIE SÚ.
grant select (model_id, connected, enabled, handle, display_name, creator_uuid,
              scope, expires_at, last_error, updated_at)
  on fanvue to authenticated;

-- fanvue_events: žiadna policy a žiadny grant = výhradne service_role
-- (worker a webhook). Surové telá udalostí nemá klient prečo vidieť.

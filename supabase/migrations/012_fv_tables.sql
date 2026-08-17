-- Fáza 3.2 — Fanvue: dátová vrstva odpisovania.
--
-- Päť tabuliek, ktoré portovaný agent (`worker/src/fanvue_agent.py` +
-- `fanvue_api.FanvueDb`) potrebuje, aby vôbec mohol odpísať: fanúšikovia,
-- archív správ, priečinky vaultu, médiá a záznam, čo komu už odišlo.
--
-- ODKIAĽ SÚ STĹPCE
-- ----------------
-- Nie z .sql snapshotu — ten pre `fv_*` v starom repozitári neexistuje (tabuľky
-- tam vznikali ručne). Zdrojom je ŽIVÁ schéma `tgai` starého projektu, prečítaná
-- cez PostgREST OpenAPI (`GET /rest/v1/` s Accept-Profile), krížovo overená proti
-- tomu, čo kód naozaj číta a zapisuje. Kontrolou prešiel každý stĺpec: žiadny,
-- na ktorý kód siaha, nechýba, a žiadny nadbytočný sa nepridal.
--
-- MULTI-TENANT TRANSFORMÁCIA (rovnaké pravidlá ako 003)
-- ----------------------------------------------------
--   * `model_id` je prvý stĺpec a je súčasťou primárneho kľúča — v predlohe bola
--     jedna modelka = jedna schéma, tu je všetko v `public`;
--   * prirodzené kľúče (`fan_uuid`, `name`, `media_uuid`) sa z jednostĺpcového PK
--     menia na zložený `(model_id, …)`, aby dve modelky mohli mať toho istého
--     fanúšika alebo rovnako pomenovaný priečinok;
--   * každý index začína `model_id` — bez neho by dotaz jednej modelky čítal
--     riadky všetkých;
--   * RLS zapnuté, `anon`/`authenticated` najprv `revoke all` (default
--     privileges v projekte dávajú novým tabuľkám plné práva — lekcia zo 007).

-- ---------------------------------------------------------------------------
-- (a) fv_users — fanúšik na Fanvue
-- ---------------------------------------------------------------------------
--
-- `tg_id` je most do Telegramu: keď sa lead podarí spojiť (checkout odkaz alebo
-- `fanmatch`), agent si k nemu vie vytiahnuť celú telegramovú históriu a
-- nezačína od nuly. Index je zámerne NEunikátny — jednoznačnosť („jeden človek
-- nemôže byť dvaja") si stráži kód cez `linked_tg_ids()` a `fanmatch.best(...,
-- taken=…)`. Unikátny index by z prehry v tej kontrole spravil výnimku uprostred
-- odpisovania; spojenie je bonus, nie podmienka, a nesmie zhodiť odpoveď.

create table fv_users (
  model_id uuid not null references models(id) on delete cascade,
  fan_uuid text not null,
  handle text not null default '',
  display_name text not null default '',
  avatar_url text not null default '',
  tg_id bigint,
  -- Vypínače na úrovni jedného chatu: `ai_enabled` je zámer majiteľa,
  -- `human_takeover` je stav („teraz píšem ja, nechaj to tak").
  ai_enabled boolean not null default true,
  human_takeover boolean not null default false,
  msg_count int not null default 0,
  spent_cents int not null default 0,
  summary text not null default '',
  facts text not null default '',
  first_seen timestamptz not null default now(),
  last_incoming_at timestamptz,
  last_reply_at timestamptz,
  stage text not null default 'discovery',
  greeted boolean not null default false,
  wants text not null default '',
  -- Ponuky: kedy naposledy, koľko ich bolo a či niektorá visí nezaplatená.
  last_offer_at timestamptz,
  offers_sent int not null default 0,
  free_photos int not null default 0,
  promised_at timestamptz,
  promised_what text not null default '',
  last_paid_ask_at timestamptz,
  pending_offer_at timestamptz,
  unbought int not null default 0,
  -- Nákupy a poďakovania.
  bought_count int not null default 0,
  last_bought_at timestamptz,
  last_thanks_at timestamptz,
  thanks_sent int not null default 0,
  last_voice_at timestamptz,
  voices_sent int not null default 0,
  primary key (model_id, fan_uuid)
);

create index fv_users_tg_idx on fv_users (model_id, tg_id) where tg_id is not null;
create index fv_users_active_idx on fv_users (model_id, last_incoming_at desc nulls last);

-- ---------------------------------------------------------------------------
-- (b) fv_messages — archív konverzácie
-- ---------------------------------------------------------------------------
--
-- `message_uuid` je id správy na strane Fanvue. Je NULLABLE a zámerne bez
-- unikátneho indexu: naše vlastné správy (poďakovanie, privítanie) ho nemajú,
-- keď ich API nevráti, a duplicitám bráni `known_message_uuids()` v kóde —
-- `reconcile` si najprv zistí, čo už má, a dopĺňa len chýbajúce. Unikátny index
-- by pri súbehu vyrobil 409 namiesto ticho preskočeného riadku.

create table fv_messages (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  fan_uuid text not null,
  role text not null check (role in ('user','assistant')),
  content text not null,
  message_uuid text,
  created_at timestamptz not null default now(),
  foreign key (model_id, fan_uuid) references fv_users(model_id, fan_uuid) on delete cascade
);

-- Poradie `id desc` je to, ako číta históriu aj `known_message_uuids`.
create index fv_messages_fan_idx on fv_messages (model_id, fan_uuid, id desc);
create index fv_messages_uuid_idx on fv_messages (model_id, fan_uuid, message_uuid)
  where message_uuid is not null;

-- ---------------------------------------------------------------------------
-- (c) fv_folders — priečinky vaultu a čo v nich je
-- ---------------------------------------------------------------------------
--
-- `role` hovorí, na čo sa priečinok používa: 'sfw' / 'nsfw' na posielanie,
-- 'post' na feed, 'ignore' sa nesiaha. Bez check constraintu — hodnoty
-- priraďuje Marek v dashboarde a nový druh nesmie čakať na migráciu.

create table fv_folders (
  model_id uuid not null references models(id) on delete cascade,
  name text not null,
  role text not null default 'ignore',
  price_cents int not null default 0,
  media_count int not null default 0,
  updated_at timestamptz not null default now(),
  primary key (model_id, name)
);

-- ---------------------------------------------------------------------------
-- (d) fv_media — jednotlivé médiá z vaultu
-- ---------------------------------------------------------------------------
--
-- Synchronizácia (`fvmedia.py`) upsertuje to, čo vidí vo vaulte. `caption`,
-- `fits`, `price_cents`, `spicy` a `active` sú NAŠE stĺpce — vo Fanvue nie sú
-- a merge-duplicates ich nechá tak, lebo ich sync do tela zápisu nedáva.

create table fv_media (
  model_id uuid not null references models(id) on delete cascade,
  media_uuid text not null,
  folder text not null default '',
  kind text not null default 'image',
  thumb_url text not null default '',
  caption text not null default '',
  fits text not null default '',
  spicy boolean not null default false,
  price_cents int not null default 0,
  active boolean not null default true,
  sent_count int not null default 0,
  synced_at timestamptz not null default now(),
  posted_at timestamptz,
  primary key (model_id, media_uuid)
);

-- `media_in(folder)` sa pýta presne na toto: priečinok + len aktívne.
create index fv_media_folder_idx on fv_media (model_id, folder) where active;

-- ---------------------------------------------------------------------------
-- (e) fv_media_sends — čo už kto videl
-- ---------------------------------------------------------------------------
--
-- Predloha mala `id bigserial` a zapisovala cez PostgREST s
-- `resolution=merge-duplicates` — čo pri PK nad `id` znamenalo obyčajný insert
-- a tá istá dvojica (médium, fanúšik) sa vedela zapísať dvakrát. Tu je PK
-- zložený z prirodzených stĺpcov, presne ako `photo_sends` v 003: upsert tým
-- dostane zmysel a `sent_media()` (jediný čitateľ) dostane tú istú množinu.

create table fv_media_sends (
  model_id uuid not null references models(id) on delete cascade,
  media_uuid text not null,
  fan_uuid text not null,
  price_cents int not null default 0,
  sent_at timestamptz not null default now(),
  primary key (model_id, media_uuid, fan_uuid),
  foreign key (model_id, media_uuid) references fv_media(model_id, media_uuid) on delete cascade,
  foreign key (model_id, fan_uuid) references fv_users(model_id, fan_uuid) on delete cascade
);

-- PK začína `media_uuid`, ale pýtame sa vždy „čo videl TENTO fanúšik".
create index fv_media_sends_fan_idx on fv_media_sends (model_id, fan_uuid);

-- ---------------------------------------------------------------------------
-- (f) RLS + granty
-- ---------------------------------------------------------------------------

alter table fv_users enable row level security;
alter table fv_messages enable row level security;
alter table fv_folders enable row level security;
alter table fv_media enable row level security;
alter table fv_media_sends enable row level security;

-- Default privileges v projekte dali novým tabuľkám plné práva pre obe roly.
revoke all on fv_users, fv_messages, fv_folders, fv_media, fv_media_sends
  from anon, authenticated;

-- fv_users / fv_messages: majiteľ ČÍTA svoje konverzácie — rovnaký tvar policy
-- ako `dm_users` / `dm_messages` v 007, aby webový prehľad chatov vedel neskôr
-- ukázať aj Fanvue. Zapisovať nesmie nič: chat vedie worker a ručný zásah do
-- histórie by mu podsunul slová, ktoré nikdy nepovedala.
create policy fv_users_owner_select on fv_users
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy fv_messages_owner_select on fv_messages
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

grant select on fv_users, fv_messages to authenticated;

-- fv_folders / fv_media / fv_media_sends: žiadna policy a žiadny grant =
-- výhradne service_role (worker). Vault sa v UI zatiaľ neukazuje; keď pribudne,
-- pridá sa policy vtedy — nie „pre istotu" dopredu.

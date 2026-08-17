-- Tenant tables — ported from the single-tenant template (tgai.* → public.*).
-- Every table gains a leading model_id (tenant key, FK to models.id).

create table persona (
  model_id uuid primary key references models(id) on delete cascade,
  name text not null default 'Modelka', age int, city text,
  language text not null default '', languages text not null default '',
  backstory text not null default '',
  tone text not null default '', msg_style text not null default '',
  boundaries text not null default '', funnel_rules text not null default '',
  cta_link text not null default '', extra_rules text not null default '',
  -- Ukážky jej vlastného písania. Model sa štýl naučí zo vzorky rádovo lepšie
  -- než zo zoznamu zákazov — toto je jediné miesto, kde vidí, ako znie ona.
  examples text not null default '',
  updated_at timestamptz not null default now()
);

create table behavior (
  model_id uuid primary key references models(id) on delete cascade,
  mode text not null default 'real',
  heat text not null default 'medium',
  slang text not null default 'light',
  no_diacritics boolean not null default true,
  activity_waves boolean not null default true,
  active_tz text not null default 'America/Los_Angeles',
  active_start_min int not null default 732,
  active_end_min int not null default 150,
  debounce_min_s int not null default 8,   debounce_max_s int not null default 25,
  read_delay_min_s int not null default 5, read_delay_max_s int not null default 45,
  reply_delay_min_s int not null default 8, reply_delay_max_s int not null default 60,
  quick_reply_chance numeric not null default 0.55,
  quick_read_max_s int not null default 5,
  quick_reply_min_s int not null default 5, quick_reply_max_s int not null default 20,
  seen_only_chance numeric not null default 0.07,
  seen_only_min_s int not null default 180, seen_only_max_s int not null default 360,
  long_pause_chance numeric not null default 0.03,
  long_pause_min_s int not null default 720, long_pause_max_s int not null default 1500,
  defer_reply_chance numeric not null default 0.0,
  defer_min_s int not null default 7200, defer_max_s int not null default 10800,
  question_chance numeric not null default 0.45,
  gag_chance numeric not null default 0.07,
  greeting_gap_hours int not null default 6,
  summary_every int not null default 10,
  max_replies_per_hour int not null default 40,
  max_links_per_hour int not null default 2,
  photo_cooldown_min int not null default 45,
  voices_enabled boolean not null default true,
  morning_enabled boolean not null default true,
  morning_max_per_day int not null default 25,
  -- Vlastný hlas cez ElevenLabs. Kľúč aj hlas sedia pri modelke, nie globálne
  -- — každý majiteľ používa svoj účet a svoje hlasy.
  eleven_key text not null default '',
  eleven_voice_id text not null default '',
  voice_ambience text not null default 'home',
  voice_strength text not null default 'real',
  voice_chance numeric not null default 0.18,
  -- v3 pole `speed` ignoruje, preto sa tempo pridáva až pri mixe cez atempo.
  voice_tempo numeric not null default 1.12,
  voice_ambience_level numeric not null default 0.05,
  updated_at timestamptz not null default now(),
  constraint behavior_mode_valid check (mode in ('real','ai')),
  constraint behavior_heat_valid check (heat in ('mild','medium','hot')),
  constraint behavior_slang_valid check (slang in ('none','light','medium'))
);

create table settings (
  model_id uuid primary key references models(id) on delete cascade,
  ai_paused boolean not null default false
);

create table dm_users (
  model_id uuid not null references models(id) on delete cascade,
  tg_id bigint not null,
  username text, first_name text, lang text,
  partner_name text not null default '',
  name_asked boolean not null default false,
  funnel_stage text not null default 'cold',
  msg_count int not null default 0,
  link_sent_at timestamptz, link_push_count int not null default 0,
  paid boolean not null default false,
  ai_enabled boolean not null default true,
  human_takeover boolean not null default false,
  summary text not null default '', summary_at_msg int not null default 0,
  style_note text not null default '',
  asked_topics jsonb not null default '{}'::jsonb,
  used_gags jsonb not null default '{}'::jsonb,
  pending_reply boolean not null default false,
  reply_after timestamptz,
  notified boolean not null default false,
  last_msg_id bigint not null default 0,
  last_photo_at timestamptz,
  last_voice_at timestamptz,
  -- Ranné oslovenie: kedy sme sa ozvali a koľkokrát po sebe neodpovedal.
  last_outreach_at timestamptz,
  outreach_silent int not null default 0,
  -- Kedy naposledy prebehlo nočné čistenie faktov pre túto konverzáciu.
  tidied_at timestamptz,
  last_incoming_at timestamptz, last_reply_at timestamptz,
  created_at timestamptz not null default now(),
  primary key (model_id, tg_id)
);

create table dm_messages (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  tg_id bigint not null,
  role text not null check (role in ('user','assistant')),
  content text not null,
  created_at timestamptz not null default now(),
  -- Fulltext nad celým archívom. `simple` konfigurácia zámerne — anglický
  -- stemmer by na chatovej hovorovej angličtine narobil viac škody než osohu.
  fts tsvector generated always as (to_tsvector('simple', content)) stored,
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Append-only fakty: nová hodnota starú neprepíše, len ju odloží.
create table facts (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  tg_id bigint not null,
  key text not null, value text not null,
  confidence numeric not null default 0.8,
  first_seen timestamptz not null default now(),
  last_confirmed timestamptz not null default now(),
  superseded_by bigint references facts(id) on delete set null,
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

create table photos (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  url text not null, caption text not null default '',
  situation text not null default '', parts text[] not null default '{}',
  spicy boolean not null default false, active boolean not null default true,
  collection text not null default '',
  sent_count int not null default 0,
  created_at timestamptz not null default now()
);

create table photo_sends (
  model_id uuid not null references models(id) on delete cascade,
  photo_id bigint not null references photos(id) on delete cascade,
  tg_id bigint not null,
  sent_at timestamptz not null default now(),
  primary key (model_id, photo_id, tg_id),
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Nahraté hlasovky. `transcript` je presné znenie — model ho dostane do
-- promptu, aby text okolo nahrávky sedel, ale do chatu ho nikdy nenapíše.
-- `fits` je Marekov popis, kedy sa nahrávka hodí; `slot='night'` je rozlúčka
-- na dobrú noc. Prázdne `url` = pripravené políčko bez zvuku, preskakuje sa.
create table voices (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  url text not null default '', transcript text not null default '',
  fits text not null default '', parts text[] not null default '{}',
  slot text not null default '',
  is_cta boolean not null default false,
  active boolean not null default true,
  sent_count int not null default 0,
  created_at timestamptz not null default now()
);

create table voice_sends (
  model_id uuid not null references models(id) on delete cascade,
  voice_id bigint not null references voices(id) on delete cascade,
  tg_id bigint not null,
  sent_at timestamptz not null default now(),
  primary key (model_id, voice_id, tg_id),
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Uzavreté sedenia: čo sa dialo v tom-ktorom rozhovore, aby si to pamätala
-- aj o mesiac, keď už je surový archív príliš dlhý na prompt.
create table episodes (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  tg_id bigint not null,
  started_at timestamptz not null, ended_at timestamptz not null,
  title text not null default '', body text not null default '',
  mood text not null default '',
  created_at timestamptz not null default now(),
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Nedokončené veci („dá vedieť, ako dopadol pohovor"), na ktoré sa má vrátiť.
create table open_loops (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  tg_id bigint not null,
  what text not null,
  created_at timestamptz not null default now(),
  closed_at timestamptz,
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Čo o sebe komu natvrdila. Bez toho si o týždeň protirečí.
create table self_claims (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  tg_id bigint not null,
  claim text not null,
  said_at timestamptz not null default now(),
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Čo sudca prepísal a prečo — na spätné ladenie, nie na chod systému.
create table judge_log (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  tg_id bigint not null,
  draft text not null, fixed text not null default '',
  reason text not null default '',
  created_at timestamptz not null default now(),
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Hlas cez ElevenLabs: kľúč a hlas sedia pri modelke, nič sa nezdieľa.
-- (stĺpce v `behavior` — pozri vyššie: eleven_key, eleven_voice_id,
--  voice_ambience, voice_strength, voice_chance, voice_tempo,
--  voice_ambience_level)

-- Archív vyrobených hlasoviek. Dnes na doladenie zvuku v dashboarde, neskôr
-- ako zásoba, z ktorej sa dá siahnuť po hotovej namiesto vyrábania novej.
create table voice_clips (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  tg_id bigint,
  text text not null default '',
  spoken text not null default '',
  ambience text not null default '',
  strength text not null default '',
  tempo numeric not null default 1.12,
  voice_id text not null default '',
  url text not null default '',
  bytes int,
  kind text not null default 'reply',
  created_at timestamptz not null default now(),
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade
);

-- Fronta na ukážky z dashboardu. Miešanie a telefónny zvuk beží na ffmpegu,
-- ktorý má worker a Vercel nie — a worker na Railway nemá port, takže sa mu
-- nedá zavolať. Požiadavka preto chodí riadkom v databáze; ukážka tak vznikne
-- tým istým reťazcom ako ostrá hlasovka a nemôžu sa rozísť.
create table voice_jobs (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  text text not null,
  voice_id text not null default '',
  eleven_key text not null default '',
  ambience text not null default 'home',
  strength text not null default 'rough',
  tempo numeric not null default 1.12,
  ambience_level numeric not null default 0.05,
  status text not null default 'pending',
  url text not null default '',
  error text not null default '',
  created_at timestamptz not null default now(),
  done_at timestamptz
);

create index dm_messages_tg_id_id_idx on dm_messages (model_id, tg_id, id desc);
create index dm_users_pending_idx on dm_users (model_id, pending_reply) where pending_reply;
create index dm_users_reply_after_idx on dm_users (model_id, reply_after) where reply_after is not null;
create index dm_users_link_sent_at_idx on dm_users (model_id, link_sent_at desc) where link_sent_at is not null;
create index facts_active_idx on facts (model_id, tg_id, key) where superseded_by is null;
-- NOTE: model_id not prepended here — uuid has no default GIN operator class
-- (would need the btree_gin extension, out of scope for this migration).
create index dm_messages_fts_idx on dm_messages using gin (fts);
create index episodes_tg_idx on episodes (model_id, tg_id, ended_at desc);
create index loops_open_idx on open_loops (model_id, tg_id) where closed_at is null;
create index self_claims_tg_idx on self_claims (model_id, tg_id, said_at desc);
create index judge_log_time_idx on judge_log (model_id, created_at desc);
create index voice_clips_time_idx on voice_clips (model_id, created_at desc);
create index voice_jobs_pending_idx on voice_jobs (model_id, id) where status = 'pending';
-- Hodinový strop odpovedí sa počíta z archívu, nie z pamäte procesu.
create index dm_messages_sent_idx
  on dm_messages (model_id, created_at desc) where role = 'assistant';
create index dm_users_outreach_idx on dm_users (model_id, last_outreach_at desc nulls first);

alter table persona enable row level security;
alter table behavior enable row level security;
alter table settings enable row level security;
alter table dm_users enable row level security;
alter table dm_messages enable row level security;
alter table facts enable row level security;
alter table photos enable row level security;
alter table photo_sends enable row level security;
alter table voices enable row level security;
alter table voice_sends enable row level security;
alter table episodes enable row level security;
alter table open_loops enable row level security;
alter table self_claims enable row level security;
alter table judge_log enable row level security;
alter table voice_clips enable row level security;
alter table voice_jobs enable row level security;

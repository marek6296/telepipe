-- Dorovnanie driftu medzi starou inštaláciou (schémy tgai/tgmio v projekte
-- „ai news") a telepipe tenant tabuľkami.
--
-- 003_tenant_tables.sql vznikol z `supabase/schema.sql` starého repa, lenže
-- ostrá databáza medzitým odišla ďalej — stĺpce nižšie v nej existujú a
-- portnutý worker ich číta aj zapisuje (`behavior.py` ich má v menu kontrolného
-- bota, `userbot.py` píše `dm_users.episode_at`). Bez nich by migrácia Simony
-- a Mio ticho zahodila ich nastavenia a worker by na zápise `episode_at`
-- padal na PGRST204.
--
-- Defaulty sú prevzaté 1:1 zo starej databázy.

alter table behavior
  add column if not exists max_outreach_per_hour int not null default 6,
  add column if not exists max_active_chats int not null default 5,
  add column if not exists chat_slot_min int not null default 45,
  add column if not exists voice_when_asked boolean not null default true,
  add column if not exists voice_when_doubted boolean not null default true,
  add column if not exists voice_when_he_voices boolean not null default true,
  add column if not exists voice_when_away boolean not null default false,
  add column if not exists voice_on_goodnight boolean not null default false,
  add column if not exists voice_when_hot boolean not null default true;

-- Kedy naposledy z konverzácie vznikla epizóda (uzavreté sedenie).
alter table dm_users
  add column if not exists episode_at timestamptz;

-- Pikantná hlasovka — protipól `photos.spicy`.
alter table voices
  add column if not exists spicy boolean not null default false;

-- Column-scoped granty na `behavior` (007) treba rozšíriť ručne — nové stĺpce
-- sa do existujúceho grantu nepridajú samy. `eleven_key` zostáva nedostupný.
-- persona/settings/photos/voices majú granty na úrovni tabuľky, tie nové
-- stĺpce pokrývajú samy; dm_users je pre klienta len na čítanie (rovnako).
grant select (max_outreach_per_hour, max_active_chats, chat_slot_min,
              voice_when_asked, voice_when_doubted, voice_when_he_voices,
              voice_when_away, voice_on_goodnight, voice_when_hot)
  on behavior to authenticated;
grant insert (max_outreach_per_hour, max_active_chats, chat_slot_min,
              voice_when_asked, voice_when_doubted, voice_when_he_voices,
              voice_when_away, voice_on_goodnight, voice_when_hot)
  on behavior to authenticated;
grant update (max_outreach_per_hour, max_active_chats, chat_slot_min,
              voice_when_asked, voice_when_doubted, voice_when_he_voices,
              voice_when_away, voice_on_goodnight, voice_when_hot)
  on behavior to authenticated;

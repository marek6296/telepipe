-- Dva per-model prepínače, ktoré config.TenantConfig.from_row už číta, ale
-- v `models` dosiaľ neexistovali — čítanie preto vždy padlo na default:
--   owner_as_client  … majiteľ píše botovi ako bežný klient (testovanie personu)
--   voice_only_ids   … Telegram id, ktorým sa odpovedá výhradne hlasovkou
alter table models
  add column if not exists owner_as_client boolean not null default false,
  add column if not exists voice_only_ids bigint[] not null default '{}';

-- Fix layer over 003_tenant_tables.sql:
--   1. Port search_messages RPC (used by db.py's /rpc/search_messages, search_archive
--      feature) — multi-tenant version, scoped by model_id.
--   2. Restore voice_clips' archive semantics: clips must survive dm_user deletion
--      (only tg_id goes null), not cascade-delete with it.

-- Prehľadávanie celého archívu konverzácie. Volá sa cez PostgREST ako RPC.
create or replace function search_messages(p_model uuid, p_tg_id bigint, p_query text, p_limit int default 6)
returns table(role text, content text, created_at timestamptz)
language sql stable security definer as $$
  select m.role, m.content, m.created_at
  from dm_messages m
  where m.tg_id = p_tg_id
    and m.model_id = p_model
    and m.fts @@ plainto_tsquery('simple', p_query)
  order by ts_rank(m.fts, plainto_tsquery('simple', p_query)) desc, m.id desc
  limit least(p_limit, 20)
$$;

revoke execute on function search_messages(uuid, bigint, text, int) from public, anon, authenticated;
grant execute on function search_messages(uuid, bigint, text, int) to service_role;

-- SECURITY DEFINER bez pripnutého search_path je klasický footgun.
alter function search_messages(uuid, bigint, text, int) set search_path = public, pg_temp;

-- voice_clips je archív — má prežiť zmazanie dm_users, len tg_id sa vynuluje.
alter table voice_clips drop constraint voice_clips_model_id_tg_id_fkey;
alter table voice_clips
  add constraint voice_clips_model_id_tg_id_fkey
  foreign key (model_id, tg_id) references dm_users(model_id, tg_id)
  on delete set null (tg_id);

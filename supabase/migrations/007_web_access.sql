-- Fáza 2 — klientský (webový) prístup k dátam.
--
-- Fáza 1 nechala všetky tabuľky s RLS ON a bez policies: worker chodí cez
-- service_role (RLS obchádza), takže klientovi sa nič nezobrazilo. Web ide
-- user-scoped klientom (anon key + session JWT) → RLS + grants sú JEDINÁ obrana.
--
-- POZOR na Supabase default privileges: `alter default privileges ... grant all
-- on tables to anon, authenticated` je v projekte nastavené, takže KAŽDÁ tabuľka
-- v `public` (aj tá, čo vznikne nižšie) dostane pri vytvorení plné práva pre
-- anon aj authenticated. Column-scoped grant by na už existujúce plné právo
-- nemal žiadny účinok — preto sa najprv všetko odoberá a potom sa pridáva len
-- to, čo klient naozaj potrebuje.

-- ---------------------------------------------------------------------------
-- (a) accounts ↔ auth.users
-- ---------------------------------------------------------------------------

-- Účet už nevzniká náhodným uuid — jeho id JE id používateľa v auth.users.
alter table accounts alter column id drop default;
alter table accounts
  add constraint accounts_id_fkey
  foreign key (id) references auth.users(id) on delete cascade;

-- Registrácia (email aj budúci Google flow) musí účet založiť sama, inak by
-- prihlásený používateľ nemal riadok v accounts a nevidel by vôbec nič.
create or replace function handle_new_user()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  insert into public.accounts (id, email) values (new.id, new.email)
  on conflict do nothing;  -- bez cieľa: pokrýva id aj unique(email)
  return new;
end;
$$;

revoke execute on function handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- (b) Grants: čistý štít
-- ---------------------------------------------------------------------------

revoke all on all tables in schema public from anon, authenticated;

-- Dodatočne k 002: trigger funkcia z 005 zostala volateľná cez /rest/v1/rpc
-- (default privileges), čo hlásil aj security advisor.
revoke execute on function provision_model_rows() from public, anon, authenticated;

-- Každá tenant policy končí poddotazom `... in (select id from models where
-- account_id = auth.uid())` — bez indexu by to bol seq scan pri každom dotaze.
create index if not exists models_account_idx on models (account_id);

-- ---------------------------------------------------------------------------
-- (b1) accounts — čítanie vlastného riadku, žiadny zápis.
--      credit_balance_usd mení výhradne worker (record_usage) / admin.
-- ---------------------------------------------------------------------------

create policy accounts_owner_select on accounts
  for select to authenticated using (id = (select auth.uid()));

grant select on accounts to authenticated;

-- ---------------------------------------------------------------------------
-- (b2) models — CRUD nad vlastnými modelkami, ale bez tajomstiev a bez statusu.
-- ---------------------------------------------------------------------------

create policy models_owner_select on models
  for select to authenticated using (account_id = (select auth.uid()));
create policy models_owner_insert on models
  for insert to authenticated with check (account_id = (select auth.uid()));
create policy models_owner_update on models
  for update to authenticated
  using (account_id = (select auth.uid()))
  with check (account_id = (select auth.uid()));
create policy models_owner_delete on models
  for delete to authenticated using (account_id = (select auth.uid()));

-- Šifrované tajomstvá von nejdú ani majiteľovi — číta ich len worker
-- (service_role) a server action so service kľúčom.
grant select (id, account_id, name, status, status_reason, claimed_by,
              heartbeat_at, tg_api_id, tg_api_hash, owner_chat_id,
              created_at, updated_at, owner_as_client, voice_only_ids)
  on models to authenticated;
-- Nová modelka vzniká vždy ako draft (default) — status si klient nezvolí.
grant insert (account_id, name) on models to authenticated;
-- status/status_reason chýbajú zámerne: menia sa len cez set_model_status
-- (whitelist prechodov nižšie), inak by RPC nemalo zmysel.
grant update (name, tg_api_id, owner_chat_id, updated_at) on models to authenticated;
grant delete on models to authenticated;

-- Jediná cesta, ako klient hýbe statusom. Prechody mimo whitelistu (napr.
-- error→active po odvolanej session, alebo čokoľvek→disabled) nedáva.
create or replace function set_model_status(p_model uuid, p_status text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_status text; v_reason text;
begin
  if not exists (
    select 1 from models
    where id = p_model and account_id = (select auth.uid())
  ) then
    raise exception 'model not found';
  end if;

  select status, status_reason into v_status, v_reason
  from models where id = p_model;

  if not (
       (v_status = 'draft'  and p_status = 'active')
    or (v_status = 'active' and p_status = 'paused')
    or (v_status = 'paused' and p_status = 'active')
    -- Po chybe sa dá skúsiť znova, ale odvolanú Telegram session neopraví
    -- reštart — tam musí klient prejsť wizardom nanovo.
    or (v_status = 'error'  and p_status = 'active'
        and v_reason is distinct from 'session_revoked')
  ) then
    raise exception 'transition % -> % not allowed', v_status, p_status;
  end if;

  update models
     set status = p_status,
         status_reason = case when p_status = 'active' then '' else status_reason end,
         updated_at = now()
   where id = p_model;
  return p_status;
end;
$$;

revoke execute on function set_model_status(uuid, text) from public, anon;
grant execute on function set_model_status(uuid, text) to authenticated;

-- ---------------------------------------------------------------------------
-- (b3) Nastavenia modelky — plný CRUD pre majiteľa.
-- ---------------------------------------------------------------------------

create policy persona_owner_all on persona
  for all to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

create policy behavior_owner_all on behavior
  for all to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

create policy settings_owner_all on settings
  for all to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

create policy photos_owner_all on photos
  for all to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

create policy voices_owner_all on voices
  for all to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

grant select, insert, update, delete on persona, settings, photos, voices to authenticated;

-- behavior: `eleven_key` je cudzí API kľúč — do prehliadača nepatrí ani
-- majiteľovi. Zapisovať ho bude fáza 3 server-side (UI ho zatiaľ nemá).
grant select (model_id, mode, heat, slang, no_diacritics, activity_waves,
              active_tz, active_start_min, active_end_min,
              debounce_min_s, debounce_max_s, read_delay_min_s, read_delay_max_s,
              reply_delay_min_s, reply_delay_max_s, quick_reply_chance,
              quick_read_max_s, quick_reply_min_s, quick_reply_max_s,
              seen_only_chance, seen_only_min_s, seen_only_max_s,
              long_pause_chance, long_pause_min_s, long_pause_max_s,
              defer_reply_chance, defer_min_s, defer_max_s,
              question_chance, gag_chance, greeting_gap_hours, summary_every,
              max_replies_per_hour, max_links_per_hour, photo_cooldown_min,
              voices_enabled, morning_enabled, morning_max_per_day,
              eleven_voice_id, voice_ambience, voice_strength, voice_chance,
              voice_tempo, voice_ambience_level, updated_at)
  on behavior to authenticated;
grant insert (model_id, mode, heat, slang, no_diacritics, activity_waves,
              active_tz, active_start_min, active_end_min,
              debounce_min_s, debounce_max_s, read_delay_min_s, read_delay_max_s,
              reply_delay_min_s, reply_delay_max_s, quick_reply_chance,
              quick_read_max_s, quick_reply_min_s, quick_reply_max_s,
              seen_only_chance, seen_only_min_s, seen_only_max_s,
              long_pause_chance, long_pause_min_s, long_pause_max_s,
              defer_reply_chance, defer_min_s, defer_max_s,
              question_chance, gag_chance, greeting_gap_hours, summary_every,
              max_replies_per_hour, max_links_per_hour, photo_cooldown_min,
              voices_enabled, morning_enabled, morning_max_per_day,
              eleven_voice_id, voice_ambience, voice_strength, voice_chance,
              voice_tempo, voice_ambience_level, updated_at)
  on behavior to authenticated;
grant update (mode, heat, slang, no_diacritics, activity_waves,
              active_tz, active_start_min, active_end_min,
              debounce_min_s, debounce_max_s, read_delay_min_s, read_delay_max_s,
              reply_delay_min_s, reply_delay_max_s, quick_reply_chance,
              quick_read_max_s, quick_reply_min_s, quick_reply_max_s,
              seen_only_chance, seen_only_min_s, seen_only_max_s,
              long_pause_chance, long_pause_min_s, long_pause_max_s,
              defer_reply_chance, defer_min_s, defer_max_s,
              question_chance, gag_chance, greeting_gap_hours, summary_every,
              max_replies_per_hour, max_links_per_hour, photo_cooldown_min,
              voices_enabled, morning_enabled, morning_max_per_day,
              eleven_voice_id, voice_ambience, voice_strength, voice_chance,
              voice_tempo, voice_ambience_level, updated_at)
  on behavior to authenticated;
grant delete on behavior to authenticated;

-- ---------------------------------------------------------------------------
-- (b4) Konverzačné/prevádzkové tabuľky — pre klienta výhradne na čítanie.
--      Píše do nich len worker; ručná úprava pamäte by rozbila konzistenciu.
-- ---------------------------------------------------------------------------

create policy dm_users_owner_select on dm_users
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy dm_messages_owner_select on dm_messages
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy facts_owner_select on facts
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy episodes_owner_select on episodes
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy open_loops_owner_select on open_loops
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy self_claims_owner_select on self_claims
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy judge_log_owner_select on judge_log
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy voice_clips_owner_select on voice_clips
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy voice_jobs_owner_select on voice_jobs
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy photo_sends_owner_select on photo_sends
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy voice_sends_owner_select on voice_sends
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

grant select on dm_users, dm_messages, facts, episodes, open_loops, self_claims,
                judge_log, voice_clips, photo_sends, voice_sends
  to authenticated;
-- voice_jobs.eleven_key je opäť cudzí API kľúč (fáza 3 ho bude plniť server-side).
grant select (model_id, id, text, voice_id, ambience, strength, tempo,
              ambience_level, status, url, error, created_at, done_at)
  on voice_jobs to authenticated;

-- ---------------------------------------------------------------------------
-- (b5) usage_events — vlastná spotreba, len čítanie. pricing: nič.
-- ---------------------------------------------------------------------------

create policy usage_events_owner_select on usage_events
  for select to authenticated using (account_id = (select auth.uid()));

grant select on usage_events to authenticated;

-- ---------------------------------------------------------------------------
-- (c) tg_login_jobs — fronta na Telegram login (Next.js nevie MTProto).
-- ---------------------------------------------------------------------------

create table tg_login_jobs (
  id bigint generated always as identity primary key,
  model_id uuid not null references models(id) on delete cascade,
  account_id uuid not null references accounts(id) on delete cascade,
  phase text not null default 'send_code'
    check (phase in ('send_code','code_sent','verify_code','need_password',
                     'verify_password','done','error')),
  phone text not null default '',
  api_id int,
  -- Všetko citlivé je šifrované rovnakým ENCRYPTION_KEY ako worker
  -- (formát nonce:ct:tag). Worker hodnoty po použití maže.
  api_hash_enc text not null default '',
  code_enc text not null default '',
  password_enc text not null default '',
  phone_code_hash text not null default '',
  tmp_session_enc text not null default '',
  error text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Kód z SMS aj tak vyprší; po 10 minútach job zahodíme aj s tajomstvami.
  expires_at timestamptz not null default now() + interval '10 minutes'
);

create index tg_login_jobs_pending_idx on tg_login_jobs (phase, id)
  where phase in ('send_code','verify_code','verify_password');
create index tg_login_jobs_model_idx on tg_login_jobs (model_id, id desc);
create index tg_login_jobs_account_idx on tg_login_jobs (account_id);

alter table tg_login_jobs enable row level security;

create policy tg_login_jobs_owner_select on tg_login_jobs
  for select to authenticated
  using (account_id = (select auth.uid())
         and model_id in (select id from models where account_id = (select auth.uid())));
create policy tg_login_jobs_owner_insert on tg_login_jobs
  for insert to authenticated
  with check (account_id = (select auth.uid())
              and model_id in (select id from models where account_id = (select auth.uid())));
create policy tg_login_jobs_owner_update on tg_login_jobs
  for update to authenticated
  using (account_id = (select auth.uid()))
  with check (account_id = (select auth.uid()));

-- Nová tabuľka dostala default privileges (plné práva pre anon aj
-- authenticated) — zhodiť a dať len to potrebné.
revoke all on tg_login_jobs from anon, authenticated;
-- *_enc a phone_code_hash von nejdú ani majiteľovi: klient ich šifruje
-- server-side a späť ich nikdy nepotrebuje.
grant select (id, model_id, account_id, phase, phone, api_id, error,
              created_at, updated_at, expires_at)
  on tg_login_jobs to authenticated;
grant insert (model_id, account_id, phase, phone, api_id, api_hash_enc)
  on tg_login_jobs to authenticated;
-- Wizard dopĺňa len kód/heslo a posúva fázu; ostatné plní worker.
grant update (code_enc, password_enc, phase, updated_at)
  on tg_login_jobs to authenticated;

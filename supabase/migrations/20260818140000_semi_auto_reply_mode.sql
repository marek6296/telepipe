-- Poloautomatický režim odpovedania (semi-auto approval).
-- Spec: docs/superpowers/specs/2026-08-18-semi-auto-reply-approval-design.md
--
-- Režim je PER KANÁL: Telegram žije na `settings`, Fanvue na `fanvue`. Off/Auto/
-- Semi + voliteľný čas do auto-odoslania (minúty; NULL = čaká navždy). Schvaľovacia
-- fronta `pending_replies` je durabilná, aby prežila presun modelky na inú repliku
-- workera (vzor podľa `voice_jobs`). Claim robí worker conditional patchom
-- (status=awaiting → sent), nie SQL RPC — rovnako ako `claim_voice_job`.

-- ===========================================================================
-- (a) Telegram režim — settings
-- ===========================================================================
-- `settings` má z 007 table-level grant (select/insert/update/delete) + policy
-- `settings_owner_all`, takže nové stĺpce zdedia práva a web ich rovno vie
-- čítať aj písať. `ai_paused` ostáva ako systémová núdzová pauza (flood),
-- nezávislá od režimu.
alter table settings
  add column if not exists tg_reply_mode text not null default 'auto'
    check (tg_reply_mode in ('off', 'auto', 'semi')),
  add column if not exists tg_fallback_minutes int
    check (tg_fallback_minutes is null or tg_fallback_minutes between 1 and 1440);

comment on column settings.tg_reply_mode is
  'Telegram režim: off = nereaguje, auto = píše sama (dnešné správanie), '
  'semi = návrhy na schválenie cez control bota.';
comment on column settings.tg_fallback_minutes is
  'Semi: po koľkých minútach bez rozhodnutia odošle prvý (AI-top) návrh. '
  'NULL = čaká navždy.';

-- ===========================================================================
-- (b) Fanvue režim — fanvue
-- ===========================================================================
-- `fanvue` má column-scoped granty (015), nové stĺpce nezdedia nič — preto
-- explicitný select+update grant. `enabled` (beh agenta) ostáva; `reply_mode`
-- riadi len správanie odpovedí.
alter table fanvue
  add column if not exists reply_mode text not null default 'auto'
    check (reply_mode in ('off', 'auto', 'semi')),
  add column if not exists fallback_minutes int
    check (fallback_minutes is null or fallback_minutes between 1 and 1440);

comment on column fanvue.reply_mode is
  'Fanvue režim: off/auto/semi. Nezávislý od Telegramu (settings.tg_reply_mode).';
comment on column fanvue.fallback_minutes is
  'Semi: minúty do auto-odoslania prvého návrhu. NULL = čaká navždy.';

grant select (reply_mode, fallback_minutes) on fanvue to authenticated;
grant update (reply_mode, fallback_minutes) on fanvue to authenticated;

-- ===========================================================================
-- (c) pending_replies — durabilná fronta čakajúcich rozhodnutí
-- ===========================================================================
create table pending_replies (
  model_id      uuid not null references models(id) on delete cascade,
  id            uuid primary key default gen_random_uuid(),
  channel       text not null check (channel in ('telegram', 'fanvue')),
  -- tg_id (ako text) alebo fan_uuid
  conv_key      text not null,
  status        text not null default 'awaiting'
    check (status in ('awaiting', 'sent', 'skipped', 'superseded')),
  -- awaiting → sent (manuálne alebo časový fallback) | skipped (Preskočiť)
  --         → superseded (fanúšik napísal novú správu)
  suggestions   jsonb not null default '[]'::jsonb,   -- ["…","…","…"] od najlepšieho
  incoming_preview text not null default '',           -- posledná správa fanúšika (do karty)
  chosen_text   text,                                  -- čo sa reálne poslalo (text/popis)
  kind          text check (kind in ('text', 'photo', 'voice')),
  media_ref     text,                                  -- photo id / fv_media uuid
  price_cents   integer check (price_cents is null or price_cents >= 0),
  control_msg_id bigint,                               -- id správy karty (edit/zrušenie)
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  decided_at    timestamptz
);

-- Poller berie awaiting najstaršie prvé; supersede hľadá otvorené pre konverzáciu.
create index pending_replies_open_idx
  on pending_replies (model_id, created_at)
  where status = 'awaiting';
create index pending_replies_conv_idx
  on pending_replies (model_id, channel, conv_key)
  where status = 'awaiting';

comment on table pending_replies is
  'Semi-auto: návrhy odpovedí čakajúce na schválenie majiteľom v control bote. '
  'Zapisuje výhradne worker (service_role); klient len číta vlastné.';

alter table pending_replies enable row level security;

-- Nová tabuľka vznikne s plnými právami pre anon+authenticated — zhodiť, potom
-- vrátiť len owner SELECT (na prípadný počet čakajúcich v dashboarde).
revoke all on pending_replies from anon, authenticated;

create policy pending_replies_owner_select on pending_replies
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

grant select (
  id, model_id, channel, conv_key, status, incoming_preview, kind,
  price_cents, created_at, updated_at, decided_at
) on pending_replies to authenticated;

-- ===========================================================================
-- (d) Poistky — grant, ktorý unikol, nech je chybou migrácie
-- ===========================================================================
do $$
begin
  -- Klient nikdy nesmie zapisovať do fronty ani čítať návrhy/text (to je obsah
  -- konverzácie, ktorý patrí do chatu, nie do zoznamu čakajúcich).
  if has_table_privilege('authenticated', 'public.pending_replies', 'INSERT')
     or has_table_privilege('authenticated', 'public.pending_replies', 'UPDATE')
     or has_table_privilege('authenticated', 'public.pending_replies', 'DELETE') then
    raise exception 'pending_replies je zapisovateľný klientom — to je service-only fronta';
  end if;
  if has_column_privilege('authenticated', 'public.pending_replies', 'suggestions', 'SELECT')
     or has_column_privilege('authenticated', 'public.pending_replies', 'chosen_text', 'SELECT') then
    raise exception 'pending_replies.suggestions/chosen_text je čitateľný klientom';
  end if;
  -- A naopak — Fanvue formulár potrebuje zapisovať režim.
  if not has_column_privilege('authenticated', 'public.fanvue', 'reply_mode', 'UPDATE') then
    raise exception 'chýba grant fanvue.reply_mode, ktorý dashboard potrebuje';
  end if;
end $$;

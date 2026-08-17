-- Fáza 3.3 — Fanvue: nastavenia agenta, vault v dashboarde a fronta synchronizácie.
--
-- ČO TO RIEŠI
-- -----------
-- Telegram a Fanvue sú dvaja agenti tej istej modelky. Telegram má celú svoju
-- tabuľku `behavior` (003) a v dashboarde k nej kartu; Fanvue mal doteraz len
-- pripojenie (011) a jediný vypínač `enabled`. Portovaný kód pritom číta ďalších
-- 21 nastavení (`fanvue_agent.py`, `fvflow.py`, `fvmedia.py`, `fvvoice.py`) —
-- bez nich beží na `or 0` fallbackoch a napríklad `offer_after_msgs = 0`
-- znamená „ponúkaj hneď od prvej správy". Táto migrácia ich dopĺňa.
--
-- ODKIAĽ SÚ DEFAULTY
-- ------------------
-- Zo ŽIVEJ schémy `tgai` starého projektu (dmxosdgvmzvkeivknczv), prečítanej
-- cez PostgREST OpenAPI. Nie z hlavy a nie z UI — hodnota, na ktorej Simone
-- rok beží produkcia, je jediná overená. Súpis stĺpec po stĺpci aj s tým, kde
-- ho worker číta, je v `docs/fanvue-settings.md`.
--
-- ČO SA ZÁMERNE NEPRENIESLO
-- -------------------------
-- `price_min_cents` / `price_max_cents` sú v starej schéme aj na starej karte,
-- ale nečíta ich ANI JEDEN riadok kódu — cena je vlastnosť fotky
-- (`fv_media.price_cents`), nie účtu. Mŕtvy stĺpec by v dashboarde klamal, že
-- niečo robí. `webhook_secret` per modelku tiež nie: appka na Fanvue je jedna
-- spoločná a podpis overuje `FANVUE_WEBHOOK_SECRET` z prostredia.
--
-- POZOR na Supabase default privileges (lekcia zo 007, 011, 014):
--   * NOVÁ TABUĽKA vznikne s plnými právami pre `anon` aj `authenticated`
--     (`alter default privileges … grant all on tables`) — preto `revoke all`
--     PRED každým column grantom, inak by column-scoped grant nemal čo obmedziť;
--   * NOVÝ STĹPEC na existujúcej tabuľke zdedí právo, ktoré má tabuľka ako
--     celok. `fanvue` má z 011 len column-scoped `select`, takže nové stĺpce
--     nezdedia nič — ale spoliehať sa na to je presne ten predpoklad, ktorý raz
--     skončí tichým únikom. Preto sa nižšie granty vymenúvajú explicitne
--     a migrácia si ich sama overí cez `has_column_privilege`.

-- ===========================================================================
-- (a) fanvue — nastavenia agenta
-- ===========================================================================

alter table fanvue
  -- Odpisovanie -------------------------------------------------------------
  add column if not exists greet_new boolean not null default true,
  add column if not exists discovery_msgs int not null default 4
    check (discovery_msgs between 0 and 20),
  add column if not exists summary_every int not null default 12
    check (summary_every between 1 and 200),
  add column if not exists heat text not null default 'hot'
    check (heat in ('mild', 'medium', 'hot')),
  add column if not exists extra_rules text not null default '',
  -- Pauza pred odpoveďou. Na Fanvue je kratšia než na Telegrame — je to
  -- platený chat a nikto tam nečaká pol hodiny.
  add column if not exists reply_min_s int not null default 20
    check (reply_min_s between 0 and 3600),
  add column if not exists reply_max_s int not null default 180
    check (reply_max_s between 0 and 3600),
  -- Vlastné okno hodín. Zóna sa NEDUPLIKUJE — berie sa `behavior.active_tz`,
  -- lebo je to vlastnosť tej osoby, nie platformy.
  add column if not exists active_start_min int not null default 0
    check (active_start_min between 0 and 1439),
  add column if not exists active_end_min int not null default 0
    check (active_end_min between 0 and 1439),

  -- Predaj ------------------------------------------------------------------
  add column if not exists sell_content boolean not null default true,
  add column if not exists offer_after_msgs int not null default 8
    check (offer_after_msgs between 0 and 200),
  add column if not exists offer_cooldown_h int not null default 12
    check (offer_cooldown_h between 0 and 720),
  -- 0 = sama s ponukou nikdy nepríde, čaká, kým si vypýta.
  add column if not exists nudge_after_msgs int not null default 25
    check (nudge_after_msgs between 0 and 500),
  add column if not exists thank_purchases boolean not null default true,
  add column if not exists voices_enabled boolean not null default false,
  add column if not exists voice_price_cents int not null default 800
    check (voice_price_cents between 0 and 100000),

  -- Fotky a feed ------------------------------------------------------------
  add column if not exists send_photos boolean not null default true,
  add column if not exists free_photo_max int not null default 2
    check (free_photo_max between 0 and 50),
  add column if not exists posting_enabled boolean not null default false,
  add column if not exists post_every_h int not null default 24
    check (post_every_h between 0 and 720),
  add column if not exists post_audience text not null default 'followers-and-subscribers'
    check (post_audience in ('subscribers', 'followers-and-subscribers')),
  -- Píše ich výhradne worker; klient ich len číta.
  add column if not exists last_post_at timestamptz,
  add column if not exists media_synced_at timestamptz;

comment on column fanvue.heat is
  'Otvorenosť na Fanvue. `hot` pridá do promptu blok fvflow.HOT. Nezávisí od '
  'behavior.heat — tam je zaplatený, tu ešte nie.';
comment on column fanvue.nudge_after_msgs is
  'Po toľkých správach príde s ponukou sama. 0 = nikdy, čaká na jeho otázku.';
comment on column fanvue.last_post_at is
  'Kedy naposledy pridala príspevok na feed. Píše worker (fanvue_agent).';
comment on column fanvue.media_synced_at is
  'Kedy naposledy prebehla synchronizácia vaultu. Píše worker (fvvault).';

-- ---------------------------------------------------------------------------
-- Granty na fanvue
-- ---------------------------------------------------------------------------
--
-- 011 dal `authenticated` iba `select` na vymenované stĺpce a žiadny `update` —
-- pripojenie prepínajú server actions so service kľúčom. Nastavenia sú ale
-- obyčajný formulár s auto-save: nechať ich ísť cez server action so service
-- kľúčom by znamenalo obísť RLS pri KAŽDOM posunutí slidera. Preto tu klient
-- dostane column-scoped `update` a rozhoduje o ňom policy, nie náš kód.
--
-- `enabled`, `connected`, tokeny, `creator_uuid`, `scope`, `handle`,
-- `display_name`, `last_error`, `last_post_at`, `media_synced_at` a
-- `updated_at` v zápisovom grante ZÁMERNE nie sú: to nie sú nastavenia, ale
-- stav pripojenia a záznam workera.

grant select (greet_new, discovery_msgs, summary_every, heat, extra_rules,
              reply_min_s, reply_max_s, active_start_min, active_end_min,
              sell_content, offer_after_msgs, offer_cooldown_h, nudge_after_msgs,
              thank_purchases, voices_enabled, voice_price_cents,
              send_photos, free_photo_max, posting_enabled, post_every_h,
              post_audience, last_post_at, media_synced_at)
  on fanvue to authenticated;

grant update (greet_new, discovery_msgs, summary_every, heat, extra_rules,
              reply_min_s, reply_max_s, active_start_min, active_end_min,
              sell_content, offer_after_msgs, offer_cooldown_h, nudge_after_msgs,
              thank_purchases, voices_enabled, voice_price_cents,
              send_photos, free_photo_max, posting_enabled, post_every_h,
              post_audience, updated_at)
  on fanvue to authenticated;

-- Bez policy by column grant nestačil — RLS je na tabuľke zapnuté z 011.
-- `with check` má rovnaký tvar ako `using`: riadok nesmie zmeniť majiteľa.
-- `model_id` je navyše mimo update grantu, takže presunúť riadok inam sa nedá
-- ani omylom.
create policy fanvue_owner_update on fanvue
  for update to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

-- ===========================================================================
-- (b) fv_folders / fv_media — vault v dashboarde
-- ===========================================================================
--
-- 012 ich nechalo výhradne service-role s poznámkou „keď to UI bude potrebovať,
-- pridá sa policy vtedy". Teraz to potrebuje: priečinku sa musí dať prideliť
-- rola a fotke cena, inak sa platený obsah buď neposiela vôbec (bez ceny), alebo
-- by odišiel zadarmo.
--
-- Klient smie ČÍTAŤ celé riadky (nič tajné v nich nie je) a MENIŤ len to, čo je
-- naše rozhodnutie. Riadky vytvára a maže výhradne synchronizácia — `insert`
-- ani `delete` klient nedostane, lebo priečinok „navyše", ktorý vo Fanvue
-- neexistuje, by len ticho nikdy nič neposlal.

create policy fv_folders_owner_select on fv_folders
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy fv_folders_owner_update on fv_folders
  for update to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

create policy fv_media_owner_select on fv_media
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy fv_media_owner_update on fv_media
  for update to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

grant select on fv_folders, fv_media to authenticated;

-- `media_count` a `name` píše sync, nie klient.
grant update (role, price_cents, updated_at) on fv_folders to authenticated;
-- `folder`, `kind`, `thumb_url`, `sent_count`, `posted_at` a `synced_at` sú
-- záznam o skutočnosti, nie nastavenie.
grant update (caption, fits, spicy, price_cents, active) on fv_media to authenticated;

-- `fv_media_sends` ostáva bez policy a bez grantu: je to prevádzkový záznam
-- workera („komu už čo odišlo") a ručná oprava by znamenala, že tá istá fotka
-- odíde druhý raz. Presne to sa má nestať.

-- ===========================================================================
-- (c) fanvue_sync_requests — fronta na načítanie vaultu
-- ===========================================================================
--
-- PREČO FRONTA A NIE PRIAME VOLANIE
-- V predlohe si synchronizáciu robil dashboard sám (Next.js volal Fanvue API
-- prístupovým tokenom z DB). V Telepipe je token šifrovaný `ENCRYPTION_KEY`om
-- a web ho zámerne nikdy nedešifruje — dešifrovací seam je jediný, vo
-- `worker/src/fanvue_tenant.py`. Web preto o synchronizáciu len POŽIADA
-- a worker ju vykoná.
--
-- Fronta je zároveň jediné miesto, kde sa dá ukázať výsledok („4 priečinky,
-- 12 nových fotiek") aj chyba — pri fire-and-forget by tlačidlo len bliklo.

create table fanvue_sync_requests (
  id bigint generated always as identity primary key,
  model_id uuid not null references models(id) on delete cascade,
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  -- null = čaká alebo beží. Vyplnené = hotovo, nech už dopadlo akokoľvek.
  finished_at timestamptz,
  ok boolean,
  folders int not null default 0,
  media_new int not null default 0,
  media_seen int not null default 0,
  error text not null default ''
);

-- Jedna čakajúca požiadavka na modelku. Dvojklik na tlačidlo tak skončí
-- konfliktom (server action ho prehltne), nie frontou piatich synchronizácií
-- za sebou. Zaseknutú požiadavku „vyprší" server action po 15 minútach —
-- vypnutý worker nesmie zablokovať tlačidlo navždy.
create unique index fanvue_sync_pending_one_idx on fanvue_sync_requests (model_id)
  where finished_at is null;
-- Takto sa pýta worker aj dashboard (posledná požiadavka modelky).
create index fanvue_sync_recent_idx on fanvue_sync_requests (model_id, id desc);

alter table fanvue_sync_requests enable row level security;

-- Nová tabuľka dostala default privileges (plné práva pre obe roly) — zhodiť.
revoke all on fanvue_sync_requests from anon, authenticated;

create policy fanvue_sync_owner_select on fanvue_sync_requests
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));
create policy fanvue_sync_owner_insert on fanvue_sync_requests
  for insert to authenticated
  with check (model_id in (select id from models where account_id = (select auth.uid())));

grant select on fanvue_sync_requests to authenticated;
-- Vyplniť smie klient jediný stĺpec: komu to patrí. Výsledok a časy sú
-- workerove — inak by si vedel „dopísať" úspešnú synchronizáciu, ktorá nebola.
grant insert (model_id) on fanvue_sync_requests to authenticated;

-- ===========================================================================
-- (d) Poistky — grant, ktorý unikol, sa musí prejaviť ako chyba migrácie
-- ===========================================================================

do $$
declare col text;
begin
  -- Tokeny a stav pripojenia klient nezapíše a tokeny ani neprečíta.
  foreach col in array array['access_token_enc', 'refresh_token_enc'] loop
    if has_column_privilege('authenticated', 'public.fanvue', col, 'SELECT')
       or has_column_privilege('authenticated', 'public.fanvue', col, 'UPDATE')
       or has_column_privilege('anon', 'public.fanvue', col, 'SELECT') then
      raise exception 'fanvue.% je pre klienta dostupný — grant unikol', col;
    end if;
  end loop;

  foreach col in array array['enabled', 'connected', 'creator_uuid', 'scope',
                             'handle', 'display_name', 'last_error',
                             'last_post_at', 'media_synced_at', 'model_id'] loop
    if has_column_privilege('authenticated', 'public.fanvue', col, 'UPDATE') then
      raise exception 'fanvue.% je zapisovateľný klientom — to je stav, nie nastavenie', col;
    end if;
  end loop;

  -- Vault: čítať áno, prepisovať fakty nie.
  foreach col in array array['media_uuid', 'folder', 'kind', 'thumb_url',
                             'sent_count', 'posted_at', 'synced_at', 'model_id'] loop
    if has_column_privilege('authenticated', 'public.fv_media', col, 'UPDATE') then
      raise exception 'fv_media.% je zapisovateľný klientom — to je záznam, nie nastavenie', col;
    end if;
  end loop;

  foreach col in array array['name', 'media_count', 'model_id'] loop
    if has_column_privilege('authenticated', 'public.fv_folders', col, 'UPDATE') then
      raise exception 'fv_folders.% je zapisovateľný klientom', col;
    end if;
  end loop;

  -- Odoslané médiá ostávajú neviditeľné aj nedotknuteľné.
  if has_column_privilege('authenticated', 'public.fv_media_sends', 'media_uuid', 'SELECT') then
    raise exception 'fv_media_sends je pre klienta čitateľný — má ostať service-only';
  end if;

  -- Výsledok synchronizácie si klient nedopíše.
  foreach col in array array['ok', 'folders', 'media_new', 'error', 'finished_at'] loop
    if has_column_privilege('authenticated', 'public.fanvue_sync_requests', col, 'INSERT')
       or has_column_privilege('authenticated', 'public.fanvue_sync_requests', col, 'UPDATE') then
      raise exception 'fanvue_sync_requests.% smie klient zapísať — to je výsledok workera', col;
    end if;
  end loop;

  -- A naopak: bez týchto grantov by formulár nastavení hlásil „permission denied".
  if not has_column_privilege('authenticated', 'public.fanvue', 'sell_content', 'UPDATE')
     or not has_column_privilege('authenticated', 'public.fv_folders', 'role', 'UPDATE')
     or not has_column_privilege('authenticated', 'public.fv_media', 'price_cents', 'UPDATE') then
    raise exception 'chýba grant, ktorý dashboard potrebuje';
  end if;
end $$;

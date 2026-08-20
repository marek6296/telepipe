-- Ďalšie funkcie control bota: uspávanie, horúci chat, týždenný súhrn.
--
-- Rovnaká pasca ako pri migrácii 20260820020000: Supabase dáva `authenticated`
-- plné práva cez default privileges, takže stĺpcové granty by sa len pridali
-- navrch a poistky proti opakovaným správam (`*_sent_at`, `hot_alert_at`) by
-- ostali zapisovateľné z prehliadača. Preto `revoke all` pred grantmi a sonda,
-- ktorá to overuje výslovne.

-- 1) Uspatie na pár hodín. `ai_paused` je ručná pauza bez konca; toto je pauza,
--    ktorá sa sama zobudí — presne to, čo klient chce, keď ide na tri hodiny
--    preč a nechce sa spoliehať, že si spomenie zapnúť ju späť.
alter table settings
  add column if not exists paused_until timestamptz;

comment on column settings.paused_until is
  'Do kedy modelka spí. Prázdne = nespí. Nezávislé od `ai_paused`: tá je '
  'pauza bez konca, toto sa samo zobudí.';

alter table control_bot_settings
  -- 2) Horúci chat: fanúšik práve tlačí na obsah alebo si pýta odkaz.
  --    Defaultne ZAPNUTÉ — je to jediná notifikácia, ktorá súvisí s peniazmi.
  add column if not exists notify_hot_lead boolean not null default true,
  -- 3) Týždenný súhrn s číslami. Defaultne zapnutý: raz za týždeň neotravuje
  --    a je to jediné miesto, kde klient vidí, či mu to celé zarába.
  add column if not exists weekly_report boolean not null default true,
  add column if not exists weekly_report_sent_at timestamptz;

comment on column control_bot_settings.notify_hot_lead is
  'Push, keď fanúšik tlačí na explicitný obsah alebo si pýta odkaz. '
  'Najviac raz za 12 h na jednu konverzáciu (`dm_users.hot_alert_at`).';
comment on column control_bot_settings.weekly_report is
  'Týždenný súhrn v pondelok ráno: nové chaty, odkazy, platby, kredit.';

-- Poistka proti druhému upozorneniu na ten istý chat.
alter table dm_users
  add column if not exists hot_alert_at timestamptz;

comment on column dm_users.hot_alert_at is
  'Kedy naposledy odišlo upozornenie na horúci chat. Worker (service role) '
  'zapisuje, klient len číta.';

-- `settings` má tiež STĹPCOVÉ granty, nie tabuľkové — nový stĺpec by inak
-- klient nevidel a tlačidlo na stránke by ukazovalo „nespí" aj počas spánku.
-- Prvý beh tejto migrácie na tom spadol.
revoke all (paused_until) on settings from authenticated;
grant select (paused_until), update (paused_until) on settings to authenticated;

revoke all (notify_hot_lead, weekly_report, weekly_report_sent_at)
  on control_bot_settings from authenticated;
grant select (notify_hot_lead, weekly_report, weekly_report_sent_at),
      update (notify_hot_lead, weekly_report)
  on control_bot_settings to authenticated;
grant insert (notify_hot_lead, weekly_report) on control_bot_settings to authenticated;

do $$
declare
  v_model uuid;
begin
  if not has_column_privilege('authenticated', 'control_bot_settings', 'notify_hot_lead', 'UPDATE')
     or not has_column_privilege('authenticated', 'control_bot_settings', 'weekly_report', 'UPDATE') then
    raise exception 'notifikácie: klient si ich nevie zapnúť';
  end if;
  -- Vodoznak posledného súhrnu smie písať len worker. Keby ho vedel prepísať
  -- klient, vypol by si tým poistku a súhrn by chodil dokola.
  if has_column_privilege('authenticated', 'control_bot_settings', 'weekly_report_sent_at', 'UPDATE') then
    raise exception 'weekly_report_sent_at: klient si vie vypnúť poistku';
  end if;
  if has_column_privilege('authenticated', 'dm_users', 'hot_alert_at', 'UPDATE') then
    raise exception 'hot_alert_at: klient to môže prepísať';
  end if;
  if not has_column_privilege('authenticated', 'settings', 'paused_until', 'SELECT') then
    raise exception 'paused_until: klient to nevidí';
  end if;

  -- Nikto nesmie migráciou uspať.
  select model_id into v_model from settings where paused_until is not null limit 1;
  if v_model is not null then
    raise exception 'paused_until: migrácia niekoho uspala';
  end if;

  raise notice 'control bot: uspávanie, horúci chat a týždenný súhrn OK';
end $$;

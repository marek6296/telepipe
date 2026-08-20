-- Vypínač štartovacej správy control bota.
--
-- „AI replying is live" chodí pri KAŽDOM štarte modelky — teda pri každom
-- nasadení workera a pri každom presune tenanta medzi replikami. Pri častých
-- deployoch je to najhlučnejšia notifikácia zo všetkých a klientovi zaplní chat
-- správami, ktoré mu nič nehovoria.
--
-- Default `true` zachováva doterajšie správanie: kto ju nechce, vypne si ju.
-- Opačný default by tichým vypnutím prekvapil toho, kto ju sledovať chce.

alter table control_bot_settings
  add column if not exists notify_startup boolean not null default true;

comment on column control_bot_settings.notify_startup is
  'Správa „AI replying is live" po štarte modelky. Chodí pri každom nasadení '
  'aj presune tenanta medzi replikami.';

grant update (notify_startup) on control_bot_settings to authenticated;
grant insert (notify_startup) on control_bot_settings to authenticated;

do $$
begin
  if not has_column_privilege('authenticated', 'control_bot_settings', 'notify_startup', 'UPDATE') then
    raise exception 'control_bot: klient nemôže vypnúť štartovaciu správu';
  end if;
  -- Pridanie stĺpca nesmie otvoriť poistky workera proti opakovaným správam.
  if has_column_privilege('authenticated', 'control_bot_settings', 'daily_report_sent_at', 'UPDATE')
     or has_column_privilege('authenticated', 'control_bot_settings', 'credits_warned_at', 'UPDATE') then
    raise exception 'control_bot: pridanie stĺpca otvorilo poistky workera';
  end if;
  raise notice 'notify_startup OK';
end $$;

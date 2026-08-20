-- Hlásenie, keď modelka spadne.
--
-- Doteraz bot hlásil len to, že BEŽÍ. O tom, že prestala odpisovať, sa klient
-- dozvedel až tým, že mu prestali chodiť správy — čiže neskoro a nepriamo.
--
-- ČO SA HLÁSI A ČO NIE
-- --------------------
-- Hlási sa PÁD. Nehlási sa riadené ukončenie (deploy, presun tenanta medzi
-- replikami) — to nie je porucha a klient by dostal správu pri každom
-- nasadení. Nehlási sa ani vyčerpaný kredit: ten má vlastnú správu, ktorá
-- rovno povie, čo s tým, a druhá by len mátla.
--
-- Default `true` zámerne: je to jediná notifikácia, ktorá hovorí, že služba
-- NEFUNGUJE. Ostatné sú informatívne a môžu byť ticho.

alter table control_bot_settings
  add column if not exists notify_crash boolean not null default true;

comment on column control_bot_settings.notify_crash is
  'Správa „She stopped replying" pri páde modelky. Riadené ukončenie ani '
  'vyčerpaný kredit sa cez ňu nehlásia.';

grant update (notify_crash) on control_bot_settings to authenticated;
grant insert (notify_crash) on control_bot_settings to authenticated;

do $$
begin
  if not has_column_privilege('authenticated', 'control_bot_settings', 'notify_crash', 'UPDATE') then
    raise exception 'control_bot: klient nemôže prepnúť hlásenie pádu';
  end if;
  if has_column_privilege('authenticated', 'control_bot_settings', 'daily_report_sent_at', 'UPDATE')
     or has_column_privilege('authenticated', 'control_bot_settings', 'credits_warned_at', 'UPDATE') then
    raise exception 'control_bot: pridanie stĺpca otvorilo poistky workera';
  end if;
  raise notice 'notify_crash OK';
end $$;

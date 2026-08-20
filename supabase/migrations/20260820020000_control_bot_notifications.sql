-- Čo má control bot modelky hlásiť majiteľovi.
--
-- Control bot je klientov vlastný bot pri každej modelke a doteraz vedel len
-- ovládať a nosiť semi-auto karty. Toto z neho robí aj notifikátor: Fanvue
-- udalosti, dochádzajúce Pipe Coiny a denný súhrn.
--
-- PREČO VLASTNÁ TABUĽKA A NIE STĹPCE V `settings`
-- ----------------------------------------------
-- `settings` číta worker pri každej odpovedi a je to horúca cesta. Prepínače
-- notifikácií sa čítajú raz za pár minút v sweeperi — pchať ich do tej istej
-- tabuľky by znamenalo ťahať ich pri každej správe zadarmo.
--
-- LEKCIA Z MIGRÁCIE 017 PLATÍ AJ TU
-- ---------------------------------
-- Supabase novej tabuľke pridelí `authenticated` plné práva cez default
-- privileges. Stĺpcové granty by sa len pridali navrch a `daily_report_sent_at`
-- by ostalo zapisovateľné — klient by si tým vypol poistku proti opakovaným
-- reportom. Prvý beh tejto migrácie na tom spadol, preto `revoke all` pred
-- grantmi. Sonda to overuje výslovne.

create table if not exists control_bot_settings (
  model_id uuid primary key references models(id) on delete cascade,

  notify_fanvue_subscribe boolean not null default true,
  notify_fanvue_payment   boolean not null default true,
  notify_fanvue_follow    boolean not null default false,
  notify_fanvue_like      boolean not null default false,
  notify_fanvue_comment   boolean not null default false,

  notify_credits_low boolean not null default true,

  daily_report boolean not null default false,
  daily_report_sent_at timestamptz,
  credits_warned_at timestamptz,

  updated_at timestamptz not null default now()
);

comment on table control_bot_settings is
  'Čo má control bot modelky hlásiť. Riadok zakladá trigger spolu s modelkou.';
comment on column control_bot_settings.daily_report is
  'Denný súhrn Telegram konverzácií po skončení aktívneho okna. VYPNUTÝ '
  'defaultne — stojí kredity a nie každý ho chce.';
comment on column control_bot_settings.daily_report_sent_at is
  'Kedy naposledy odišiel. Sweeper beží každé tri minúty, takže bez tejto '
  'značky by report v okne po konci odišiel tridsaťkrát. Patrí WORKEROVI.';
comment on column control_bot_settings.credits_warned_at is
  'Kedy odišlo upozornenie na dochádzajúce coiny. Nuluje sa, keď zostatok '
  'znova stúpne — inak by po dobití druhé upozornenie už neprišlo.';
comment on column control_bot_settings.notify_fanvue_follow is
  'Vypnuté defaultne: nie je overené, že Fanvue follow event vôbec posiela. '
  'Za týždeň prevádzky prišli len lajky, komentáre a správy.';

alter table control_bot_settings enable row level security;

drop policy if exists control_bot_settings_owner_all on control_bot_settings;
create policy control_bot_settings_owner_all on control_bot_settings
  for all
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

revoke all on control_bot_settings from authenticated, anon;

grant select on control_bot_settings to authenticated;
grant insert (model_id, notify_fanvue_subscribe, notify_fanvue_payment,
              notify_fanvue_follow, notify_fanvue_like, notify_fanvue_comment,
              notify_credits_low, daily_report, updated_at)
  on control_bot_settings to authenticated;
grant update (notify_fanvue_subscribe, notify_fanvue_payment, notify_fanvue_follow,
              notify_fanvue_like, notify_fanvue_comment, notify_credits_low,
              daily_report, updated_at)
  on control_bot_settings to authenticated;

create or replace function provision_model_rows()
returns trigger language plpgsql security definer
set search_path to 'public', 'pg_temp' as $$
begin
  insert into persona              (model_id) values (new.id) on conflict do nothing;
  insert into behavior             (model_id) values (new.id) on conflict do nothing;
  insert into settings             (model_id) values (new.id) on conflict do nothing;
  insert into model_schedule       (model_id) values (new.id) on conflict do nothing;
  insert into control_bot_settings (model_id) values (new.id) on conflict do nothing;
  return new;
end;
$$;

insert into control_bot_settings (model_id)
select id from models on conflict do nothing;

do $$
declare
  v_zapnuty boolean;
  v_pocet int;
begin
  select count(*) into v_pocet from models m
   where not exists (select 1 from control_bot_settings s where s.model_id = m.id);
  if v_pocet > 0 then
    raise exception 'control_bot: % modeliek nemá riadok nastavení', v_pocet;
  end if;

  -- Poistky workera klient prepísať NESMIE — inak si ich vypne a dostane
  -- report tridsaťkrát alebo upozornenie na kredit nikdy.
  if has_column_privilege('authenticated', 'control_bot_settings', 'daily_report_sent_at', 'UPDATE') then
    raise exception 'control_bot: klient smie prepísať daily_report_sent_at';
  end if;
  if has_column_privilege('authenticated', 'control_bot_settings', 'credits_warned_at', 'UPDATE') then
    raise exception 'control_bot: klient smie prepísať credits_warned_at';
  end if;
  if has_column_privilege('authenticated', 'control_bot_settings', 'model_id', 'UPDATE') then
    raise exception 'control_bot: klient smie prepísať model_id — privlastnil by si cudzí riadok';
  end if;

  -- Prepínače naopak nastaviť MUSÍ, inak by formulár ticho nič nerobil.
  if not has_column_privilege('authenticated', 'control_bot_settings', 'daily_report', 'UPDATE')
     or not has_column_privilege('authenticated', 'control_bot_settings', 'notify_credits_low', 'UPDATE') then
    raise exception 'control_bot: klient nemôže prepnúť notifikácie';
  end if;

  select daily_report into v_zapnuty from control_bot_settings limit 1;
  if v_zapnuty then
    raise exception 'control_bot: denný report je defaultne zapnutý, hoci stojí kredity';
  end if;

  raise notice 'control_bot_settings OK';
end $$;

-- Notifikácie — zvonček v appke (vrstva 2 z 3: gating → notifikácie → chat).
--
-- PREČO TRIGGERY A NIE WORKER
-- ---------------------------
-- Všetky prevádzkové notifikácie vznikajú z triggerov nad zmenami, ktoré worker
-- do databázy zapisuje aj dnes. Keby ich posielal worker, museli by sme ho
-- meniť pri každom novom druhu — a hlavne by nevznikli nikdy, keď tú istú zmenu
-- spraví web alebo Marek ručne v SQL. Worker sa touto migráciou NEDOTÝKA.
--
-- NOTIFIKÁCIA NESMIE ZHODIŤ ZÁPIS POD SEBOU
-- -----------------------------------------
-- Triggery visia na `accounts` (píše doň `record_usage`) a na `models`/`settings`
-- (píše do nich worker). Keby trigger vyhodil výnimku, vzal by so sebou
-- fakturáciu alebo beh agenta. Preto každý z nich chybu PREHLTNE — zvonček je
-- nice-to-have, zápis pod ním je kritický. Sonda to overuje.

-- ---------------------------------------------------------------------------
-- (a) Tabuľka
-- ---------------------------------------------------------------------------

create table if not exists notifications (
  id         uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  kind       text not null check (kind in (
               'access_approved', 'access_rejected',
               'model_error', 'model_muted', 'credits_low')),
  title      text not null,
  body       text not null default '',
  href       text not null default '',
  read_at    timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists notifications_account_recent
  on notifications (account_id, created_at desc);

-- Zvonček sa pri každom načítaní stránky pýta „mám niečo neprečítané?".
create index if not exists notifications_unread
  on notifications (account_id) where read_at is null;

-- ---------------------------------------------------------------------------
-- (b) RLS — čítať svoje, meniť LEN `read_at`
-- ---------------------------------------------------------------------------
--
-- Granty po stĺpcoch, nie na tabuľku: table-level grant v tomto projekte už raz
-- ticho prebil neskorší column-level revoke a odhalil cudzí ElevenLabs kľúč
-- (migrácia 017). Odvtedy je každý nový stĺpec skrytý, kým ho niekto vedome
-- nepovolí.

alter table notifications enable row level security;
revoke all on notifications from anon, authenticated;
grant select (id, account_id, kind, title, body, href, read_at, created_at)
  on notifications to authenticated;
grant update (read_at) on notifications to authenticated;

drop policy if exists notifications_owner_select on notifications;
create policy notifications_owner_select on notifications
  for select to authenticated using (account_id = (select auth.uid()));

drop policy if exists notifications_owner_update on notifications;
create policy notifications_owner_update on notifications
  for update to authenticated
  using (account_id = (select auth.uid()))
  with check (account_id = (select auth.uid()));

-- Žiadny INSERT ani DELETE policy ZÁMERNE: notifikácie vyrába výhradne
-- `notify_account()`, inak by si ich klient vedel vyrobiť alebo zahladiť.

-- ---------------------------------------------------------------------------
-- (c) notify_account() — JEDINÉ miesto, kde notifikácia vzniká
-- ---------------------------------------------------------------------------
--
-- Dedupe je jej hlavná úloha, nie doplnok: `credits_low` by inak vznikla pri
-- každom jednom LLM volaní pod prahom a klient by mal do minúty stovku riadkov.

create or replace function notify_account(
  p_account uuid,
  p_kind    text,
  p_title   text,
  p_body    text default '',
  p_href    text default '',
  p_dedupe  interval default interval '0 seconds'
)
returns uuid language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_id uuid;
begin
  if p_account is null then return null; end if;

  if p_dedupe > interval '0 seconds' and exists (
    select 1 from notifications
     where account_id = p_account and kind = p_kind
       and created_at > now() - p_dedupe
  ) then
    return null;
  end if;

  insert into notifications (account_id, kind, title, body, href)
  values (p_account, p_kind, p_title, coalesce(p_body, ''), coalesce(p_href, ''))
  returning id into v_id;
  return v_id;
end;
$$;

revoke execute on function notify_account(uuid, text, text, text, text, interval)
  from public, anon, authenticated;
grant execute on function notify_account(uuid, text, text, text, text, interval)
  to service_role;

comment on function notify_account(uuid, text, text, text, text, interval) is
  'Jediné miesto, kde vzniká notifikácia. p_dedupe zahodí opakovanie toho istého druhu v okne — bez neho by credits_low vznikla pri každom LLM volaní.';

-- ---------------------------------------------------------------------------
-- (d) Producenti
-- ---------------------------------------------------------------------------

-- (d1) Modelka spadla: status → 'error'.
-- `paused` ZÁMERNE nenotifikuje — to je klientov vlastný power button.
create or replace function notify_model_error()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if new.status = 'error' and old.status is distinct from 'error' then
    begin
      perform notify_account(
        new.account_id, 'model_error',
        new.name || ' stopped',
        coalesce(nullif(new.status_reason, ''), 'The agent hit an error and is no longer running.'),
        '/app/m/' || new.id::text || '/telegram',
        interval '1 hour');
    exception when others then null;  -- notifikácia nesmie zhodiť worker
    end;
  end if;
  return new;
end;
$$;

drop trigger if exists models_notify_error on models;
create trigger models_notify_error after update on models
  for each row execute function notify_model_error();

-- (d2) Modelka prestala odpisovať: worker si po flood warningu sám nastaví
-- `ai_paused`. Klient inak pozerá na zelené „Active" a nechápe.
create or replace function notify_model_muted()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_account uuid; v_name text;
begin
  if new.ai_paused and not coalesce(old.ai_paused, false) then
    begin
      select m.account_id, m.name into v_account, v_name
        from models m where m.id = new.model_id;
      perform notify_account(
        v_account, 'model_muted',
        coalesce(v_name, 'Your agent') || ' stopped replying',
        'Replies are paused. Open the agent to resume them.',
        '/app/m/' || new.model_id::text || '/telegram',
        interval '1 hour');
    exception when others then null;
    end;
  end if;
  return new;
end;
$$;

drop trigger if exists settings_notify_muted on settings;
create trigger settings_notify_muted after update on settings
  for each row execute function notify_model_muted();

-- (d3) Dochádzajú coiny. Prah $5 ≈ 5000 Pipe Coinov.
-- Podmienka je na PRECHODE cez prah, nie na „je pod prahom" — inak by sa
-- spúšťala pri každom účtovaní. `unlimited` účty sa preskakujú, tým nič nedochádza.
create or replace function notify_credits_low()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if coalesce(new.unlimited, false) then return new; end if;
  if new.credit_balance_usd < 5 and coalesce(old.credit_balance_usd, 0) >= 5 then
    begin
      perform notify_account(
        new.id, 'credits_low',
        'Pipe Coins running low',
        'Top up to keep your agents replying.',
        '/app/billing',
        interval '24 hours');
    exception when others then null;  -- notifikácia nesmie zhodiť record_usage
    end;
  end if;
  return new;
end;
$$;

drop trigger if exists accounts_notify_credits_low on accounts;
create trigger accounts_notify_credits_low after update on accounts
  for each row execute function notify_credits_low();

-- (d4) Rozhodnutie o žiadosti — dopísané do JADRA z vrstvy 1, takže notifikáciu
-- vyrobí obe cesty naraz (web aj Telegram tlačidlo). Presne preto to jadro
-- vzniklo ako jedno.
create or replace function decide_access_request(
  p_id uuid, p_approve boolean, p_note text, p_actor uuid
)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid; v_status text; v_next text; v_note text;
begin
  select account_id, status into v_account, v_status
    from access_requests where id = p_id for update;
  if v_account is null then raise exception 'request not found'; end if;
  if v_status <> 'pending' then return v_status; end if;

  v_next := case when p_approve then 'approved' else 'rejected' end;
  v_note := left(coalesce(p_note, ''), 500);

  update access_requests
     set status = v_next, decided_at = now(), decided_by = p_actor, decided_note = v_note
   where id = p_id;

  if p_approve then
    insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                    amount, note)
    values (v_account, p_actor,
            coalesce((select email from accounts where id = v_account), ''),
            coalesce((select email from accounts where id = p_actor), ''),
            0, 'access approved -> plan=free_plus');
    update accounts set plan = 'free_plus' where id = v_account and plan = 'free';
  end if;

  begin
    if p_approve then
      perform notify_account(v_account, 'access_approved',
        'Your account is approved',
        'Everything is unlocked — you can set up your first agent now.',
        '/app');
    else
      perform notify_account(v_account, 'access_rejected',
        'Your request was not approved',
        nullif(v_note, ''), '/locked');
    end if;
  exception when others then null;  -- schválenie nesmie padnúť na notifikácii
  end;

  return v_next;
end;
$$;

revoke execute on function decide_access_request(uuid, boolean, text, uuid)
  from public, anon, authenticated;
grant execute on function decide_access_request(uuid, boolean, text, uuid) to service_role;

-- ---------------------------------------------------------------------------
-- (e) Realtime
-- ---------------------------------------------------------------------------
--
-- Realtime rešpektuje RLS, takže každý klient dostane iba svoje riadky.
-- Počúvame len INSERT — nič iné zvonček nepotrebuje.

do $$
begin
  if not exists (
    select 1 from pg_publication_tables
     where pubname = 'supabase_realtime' and schemaname = 'public'
       and tablename = 'notifications'
  ) then
    alter publication supabase_realtime add table notifications;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- (f) Sonda
-- ---------------------------------------------------------------------------

do $$
declare
  v_probe uuid; v_super uuid;
  v_role_before text; v_plan_before text; v_balance_before numeric;
  v_notifs_before bigint;
  v_n1 uuid; v_n2 uuid;
  v_dedupe_ok boolean := false;
  v_insert_blocked boolean := false;
  v_delete_blocked boolean := false;
  v_title_blocked boolean := false;
  v_read_ok boolean := false;
  v_foreign_hidden boolean := false;
  v_low_count int := 0;
  v_survives_bad_trigger boolean := false;
  v_reached boolean := false;
begin
  -- Nesuperadmin a NE-VIP: sonda tak nikdy nesiahne na skutočný platiaci účet,
  -- aj keď je celá odrolovaná (rovnaký výber ako v 021/024).
  select id, role, plan, credit_balance_usd
    into v_probe, v_role_before, v_plan_before, v_balance_before
  from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;
  select id into v_super from accounts where role = 'superadmin' order by created_at limit 1;
  select count(*) into v_notifs_before from notifications;

  if v_probe is null or v_super is null then
    raise notice 'notifications: sonda preskocena — chyba vhodny ucet';
  else
    begin
      -- (1) Vznik + dedupe
      v_n1 := notify_account(v_probe, 'credits_low', 'prva', '', '', interval '1 hour');
      v_n2 := notify_account(v_probe, 'credits_low', 'druha', '', '', interval '1 hour');
      v_dedupe_ok := (v_n1 is not null and v_n2 is null);

      -- Cudzia notifikacia MUSI existovat, inak by bol test (3) prazdny a presiel
      -- by aj s uplne rozbitou RLS.
      perform notify_account(v_super, 'credits_low', 'cudzia — probe nesmie vidiet');

      -- (2) Klient si nesmie notifikaciu vyrobit ani zmazat, ani prepisat text
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe, 'role', 'authenticated')::text, true);
      begin
        execute 'set local role authenticated';
        begin
          insert into notifications (account_id, kind, title)
          values (v_probe, 'credits_low', 'podvrh');
        exception when others then v_insert_blocked := true;
        end;
        begin
          delete from notifications where id = v_n1;
          if not found then v_delete_blocked := true; end if;
        exception when others then v_delete_blocked := true;
        end;
        begin
          update notifications set title = 'prepisane' where id = v_n1;
          if not found then v_title_blocked := true; end if;
        exception when others then v_title_blocked := true;
        end;
        begin
          update notifications set read_at = now() where id = v_n1;
          v_read_ok := found;
        exception when others then v_read_ok := false;
        end;
        -- (3) Cudzie notifikacie nesmie vidiet
        begin
          v_foreign_hidden := not exists (
            select 1 from notifications where account_id = v_super);
        exception when others then v_foreign_hidden := true;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
      end;
      perform set_config('request.jwt.claims', '', true);

      -- (4) Trigger na coiny: prechod cez prah vyrobi PRESNE jednu
      delete from notifications where account_id = v_probe;
      update accounts set credit_balance_usd = 100, unlimited = false where id = v_probe;
      update accounts set credit_balance_usd = 2 where id = v_probe;
      update accounts set credit_balance_usd = 1 where id = v_probe;  -- uz pod prahom, nesmie pridat
      select count(*) into v_low_count from notifications
       where account_id = v_probe and kind = 'credits_low';

      -- (5) NAJDOLEZITEJSIE: pokazeny trigger NESMIE zhodit zapis pod sebou.
      --     Docasne prepiseme notify_account tak, aby vzdy padla.
      create or replace function notify_account(
        p_account uuid, p_kind text, p_title text,
        p_body text default '', p_href text default '',
        p_dedupe interval default interval '0 seconds')
      returns uuid language plpgsql security definer
      set search_path = public, pg_temp as 'begin raise exception ''sonda: notify_account padla''; end;';

      begin
        update accounts set credit_balance_usd = 500 where id = v_probe;
        update accounts set credit_balance_usd = 1 where id = v_probe;
        v_survives_bad_trigger := true;   -- zapis presiel napriek padajucej notifikacii
      exception when others then v_survives_bad_trigger := false;
      end;

      v_reached := true;
      raise exception 'notifications-sonda-rollback' using errcode = 'P0001';
    exception when raise_exception then
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then raise exception 'notifications: sonda spadla skor, nez dobehla'; end if;
    if not v_dedupe_ok then raise exception 'notifications: dedupe nefunguje — credits_low by sa mnozila'; end if;
    if not v_insert_blocked then raise exception 'notifications: KLIENT SI VYROBIL NOTIFIKACIU'; end if;
    if not v_delete_blocked then raise exception 'notifications: klient dokazal zmazat notifikaciu'; end if;
    if not v_title_blocked then raise exception 'notifications: klient prepisal title'; end if;
    if not v_read_ok then raise exception 'notifications: klient si nedokaze oznacit precitane'; end if;
    if not v_foreign_hidden then raise exception 'notifications: KLIENT VIDI CUDZIE NOTIFIKACIE'; end if;
    if v_low_count <> 1 then raise exception 'notifications: prechod cez prah vyrobil % notifikacii namiesto 1', v_low_count; end if;
    if not v_survives_bad_trigger then raise exception 'notifications: PADAJUCA NOTIFIKACIA ZHODILA ZAPIS DO accounts — ohrozuje uctovanie'; end if;

    if (select count(*) from notifications) <> v_notifs_before then
      raise exception 'notifications: sonda po sebe nechala notifikacie';
    end if;
    if exists (
      select 1 from accounts
      where id = v_probe and (role <> v_role_before or plan <> v_plan_before
                              or credit_balance_usd <> v_balance_before)
    ) then
      raise exception 'notifications: sonda po sebe nechala zmeneny ucet';
    end if;
  end if;
end $$;

-- Uvítanie po schválení prístupu: štartovací kredit + značka „návod videný".
--
-- ČO TO RIEŠI
-- -----------
-- Po schválení sa človeku odomkne všetko naraz a on stojí pred prázdnym
-- dashboardom. Uvítacie okno mu povie, čím začať (napojiť modelke Telegram)
-- a že na rozbeh dostal kredit.
--
-- Aby to okno nehovorilo nepravdu, kredit musí naozaj dostať — doteraz mu ho
-- Marek pripisoval ručne. Tu sa pripíše sám pri schválení.
--
-- DVE VECI, KTORÉ SÚ TU ZÁMERNE
-- -----------------------------
-- 1. Suma je v `app_config` (`signup_credit_usd`), nie natvrdo. Sedí tak
--    s ostatnými cenami a superadmin ju vie zmeniť z admin panela bez
--    migrácie. `admin_set_config` pustí každý kľúč, ktorý v tabuľke existuje.
--
-- 2. Kredit sa pripíše NAJVIAC RAZ za účet. Značkou je riadok v
--    `credit_adjustments` s poznámkou `signup credit` — ten istý ledger, kde
--    sú aj ručné úpravy, takže sa to dá dohľadať a nepotrebuje to vlastný
--    stĺpec. Bez tejto poistky by druhá žiadosť po zamietnutí priniesla druhý
--    kredit a dal by sa tak ťahať donekonečna.

-- ---------------------------------------------------------------------------
-- (a) Suma štartovacieho kreditu
-- ---------------------------------------------------------------------------

insert into app_config (key, value) values ('signup_credit_usd', 5.00)
on conflict (key) do nothing;

comment on table app_config is
  'Ceny a marže platformy. `signup_credit_usd` je kredit pripísaný pri prvom '
  'schválení prístupu; 0 ho vypne.';

-- ---------------------------------------------------------------------------
-- (b) Značka, že človek videl uvítanie
-- ---------------------------------------------------------------------------
--
-- POZOR (lekcia z migrácie 017): `accounts` nemá tabuľkový grant, iba stĺpcové
-- SELECT-y. Nový stĺpec preto NIE JE automaticky viditeľný ani zapisovateľný —
-- čítanie treba povoliť ručne a zápis nechať výhradne cez RPC nižšie. Keby sa
-- sem omylom dostalo UPDATE, klient by si vedel prepísať čokoľvek v tom stĺpci.

alter table accounts add column if not exists onboarding_done_at timestamptz;

grant select (onboarding_done_at) on accounts to authenticated;

comment on column accounts.onboarding_done_at is
  'Kedy človek zavrel uvítacie okno. Zapisuje LEN mark_onboarding_done().';

create or replace function mark_onboarding_done()
returns timestamptz language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_at timestamptz;
begin
  if auth.uid() is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  -- `coalesce` drží prvý čas: druhé zavretie okna dátum neprepíše, takže sa dá
  -- z neho čítať, kedy človek naozaj začal.
  update accounts
     set onboarding_done_at = coalesce(onboarding_done_at, now())
   where id = auth.uid()
  returning onboarding_done_at into v_at;
  return v_at;
end;
$$;

revoke execute on function mark_onboarding_done() from public, anon;
grant execute on function mark_onboarding_done() to authenticated;

-- ---------------------------------------------------------------------------
-- (c) decide_access_request — pri schválení pripíše štartovací kredit
-- ---------------------------------------------------------------------------
--
-- Mení sa JEDINÁ vec: blok `if p_approve`. Zvyšok (prechod stavu, zmena plánu,
-- notifikácia v `begin/exception` aby zlyhanie oznámenia nezhodilo schválenie)
-- ostáva slovo za slovom rovnaký.

create or replace function decide_access_request(p_id uuid, p_approve boolean, p_note text, p_actor uuid)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid; v_status text; v_next text; v_note text;
  v_credit numeric; v_email text; v_admin_email text;
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
    select coalesce(email, '') into v_email from accounts where id = v_account;
    select coalesce(email, '') into v_admin_email from accounts where id = p_actor;

    insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                    amount, note)
    values (v_account, p_actor, coalesce(v_email, ''), coalesce(v_admin_email, ''),
            0, 'access approved -> plan=free_plus');

    update accounts set plan = 'free_plus' where id = v_account and plan = 'free';

    -- Štartovací kredit — najviac raz za účet.
    v_credit := config_value('signup_credit_usd', 0);
    if v_credit > 0 and not exists (
      select 1 from credit_adjustments
       where account_id = v_account and note like 'signup credit%'
    ) then
      update accounts
         set credit_balance_usd = credit_balance_usd + v_credit
       where id = v_account;

      insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                      amount, note)
      values (v_account, p_actor, coalesce(v_email, ''), coalesce(v_admin_email, ''),
              v_credit, 'signup credit');
    end if;
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
  exception when others then null;
  end;

  return v_next;
end;
$$;

-- ---------------------------------------------------------------------------
-- (d) Sonda
-- ---------------------------------------------------------------------------

do $$
declare
  v_probe uuid;
  v_req uuid;
  v_credit numeric;
  v_pred numeric; v_po numeric; v_po_druhom numeric;
  v_stav text;
  v_reached boolean := false;
begin
  -- (1) Zápis do nového stĺpca nesmie mať klient. Toto je tá kontrola, ktorá
  --     v 017 chýbala a stála nás dieru.
  if has_column_privilege('authenticated', 'accounts', 'onboarding_done_at', 'UPDATE') then
    raise exception 'onboarding: klient smie zapisovať onboarding_done_at';
  end if;
  if not has_column_privilege('authenticated', 'accounts', 'onboarding_done_at', 'SELECT') then
    raise exception 'onboarding: klient nevidí onboarding_done_at, okno by sa ukazovalo stále';
  end if;

  if config_value('signup_credit_usd', -1) < 0 then
    raise exception 'onboarding: chýba kľúč signup_credit_usd';
  end if;

  select id into v_probe from accounts where role <> 'superadmin' order by created_at limit 1;
  if v_probe is null then
    raise notice 'onboarding: sonda preskočená — chýba vhodný účet';
  else
    begin
      v_credit := config_value('signup_credit_usd', 0);
      -- Účet bez akéhokoľvek štartovacieho kreditu v histórii, nech test meria
      -- prvé schválenie a nie náhodou druhé.
      delete from credit_adjustments where account_id = v_probe and note like 'signup credit%';
      select credit_balance_usd into v_pred from accounts where id = v_probe;

      insert into access_requests (account_id, status) values (v_probe, 'pending')
      returning id into v_req;
      perform decide_access_request(v_req, true, 'probe', v_probe);
      select credit_balance_usd into v_po from accounts where id = v_probe;

      -- (2) Druhá žiadosť NESMIE priniesť druhý kredit — inak sa dá ťahať
      --     donekonečna cez zamietnutie a novú žiadosť.
      insert into access_requests (account_id, status) values (v_probe, 'pending')
      returning id into v_req;
      perform decide_access_request(v_req, true, 'probe 2', v_probe);
      select credit_balance_usd into v_po_druhom from accounts where id = v_probe;

      -- (3) Rozhodnutá žiadosť sa nerozhoduje druhýkrát.
      v_stav := decide_access_request(v_req, false, 'probe 3', v_probe);

      v_reached := true;
      raise exception 'onboarding-probe-rollback';
    exception when others then
      if sqlerrm <> 'onboarding-probe-rollback' then raise; end if;
    end;

    if not v_reached then
      raise exception 'onboarding: sonda nedobehla';
    end if;
    if round(v_po - v_pred, 6) <> round(v_credit, 6) then
      raise exception 'onboarding: schválenie pripísalo % namiesto %', v_po - v_pred, v_credit;
    end if;
    if v_po_druhom <> v_po then
      raise exception 'onboarding: druhé schválenie pripísalo kredit znova (% -> %)', v_po, v_po_druhom;
    end if;
    if v_stav <> 'approved' then
      raise exception 'onboarding: rozhodnutá žiadosť sa dá prerozhodnúť (vrátila %)', v_stav;
    end if;
  end if;

  raise notice 'onboarding: štartovací kredit + značka OK';
end $$;

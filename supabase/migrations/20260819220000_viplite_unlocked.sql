-- `vip_lite` patrí medzi odomknuté plány.
--
-- ČO SA STALO
-- -----------
-- Migrácia 20260819160000 zaviedla plán `vip_lite` (1.5× nákupka, plán pre
-- partnerov) a poctivo ho dopísala do `accounts_plan_check`, `record_usage`
-- aj `admin_set_plan` — vrátane toho, že mu nastaví `access_granted_at`.
--
-- Nedopísala ho ale do `account_unlocked()`. Tá stále poznala len
-- `('free_plus', 'vip')`, takže partner prepnutý na `vip_lite` mal síce
-- schválený prístup a správne účtovanie, ale RLS `models_owner_insert` mu
-- NEDOVOLILA založiť modelku — appka ho poslala na `/locked`. Účet by vyzeral
-- schválený a zároveň zamknutý.
--
-- Chytilo sa to skôr, než na tom plán ktokoľvek bol (`select count(*) from
-- accounts where plan='vip_lite'` = 0), takže sa nič neopravuje spätne.
--
-- PREČO SA TO DALO PREHLIADNUŤ
-- ----------------------------
-- Pravidlo odomknutia je vymenované na dvoch miestach — tu a v `lib/access.ts`
-- — a pribudnutie plánu si žiada zásah do oboch. Sonda nižšie preto netestuje
-- konkrétne plány, ale INVARIANT: čokoľvek, čo prejde cez `accounts_plan_check`
-- a nie je `free`, musí byť odomknuté. Ďalší plán tak spadne tu a nie u klienta.

-- ---------------------------------------------------------------------------
-- (a) account_unlocked — pribúda vip_lite
-- ---------------------------------------------------------------------------

create or replace function account_unlocked(p_account uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
  select exists (
    select 1 from accounts
    where id = p_account
      and (plan in ('free_plus', 'vip_lite', 'vip') or role in ('admin', 'superadmin'))
  );
$$;

revoke execute on function account_unlocked(uuid) from public, anon;
grant execute on function account_unlocked(uuid) to authenticated, service_role;

comment on function account_unlocked(uuid) is
  'Smie tento účet pracovať? Jediný zdroj pravdy — používa ho RLS na models '
  'INSERT aj web (lib/access.ts). Odomyká každý plán okrem free '
  '(free_plus/vip_lite/vip) alebo rolu admin/superadmin.';

-- ---------------------------------------------------------------------------
-- (b) Sonda — dieru v zámku musí zachytiť migrácia, nie partner
-- ---------------------------------------------------------------------------
--
-- Beží na existujúcom nesuperadmin a NE-VIP účte; všetko, čo zmení, sa zahodí
-- sentinel výnimkou (vnútorný `begin ... exception` je implicitný savepoint).
-- Rovnaký postup ako 021/024 a 20260819120000.

do $$
declare
  v_probe uuid;
  v_role_before text; v_plan_before text;
  v_plan text;
  v_zamknute text[] := '{}';
  v_free_odomknute boolean := false;
  v_lite_moze boolean := false;
  v_free_blokovany boolean := false;
  v_preco text := '';
  v_reached boolean := false;
begin
  select id, role, plan into v_probe, v_role_before, v_plan_before
  from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;

  if v_probe is null then
    raise notice 'viplite-unlock: sonda preskočená — chýba vhodný účet';
  else
    begin
      -- (1) INVARIANT: každý plán z `accounts_plan_check` okrem `free` musí byť
      --     odomknutý. Toto je tá kontrola, ktorá by bola chytila `vip_lite`.
      update accounts set role = 'user' where id = v_probe;
      foreach v_plan in array array['free', 'free_plus', 'vip_lite', 'vip'] loop
        update accounts set plan = v_plan where id = v_probe;
        if v_plan = 'free' then
          v_free_odomknute := account_unlocked(v_probe);
        elsif not account_unlocked(v_probe) then
          v_zamknute := v_zamknute || v_plan;
        end if;
      end loop;

      -- (2) RLS naostro: `vip_lite` MUSÍ vedieť založiť modelku. Volanie
      --     `account_unlocked()` samo osebe nestačí — zámok je v politike, nie
      --     vo funkcii, a testovať sa dá len spod role `authenticated`
      --     (vlastník tabuľky RLS obchádza).
      --
      --     Slot musí byť voľný, inak by INSERT zhodil trigger
      --     `models_slot_limit` a sonda by to čítala ako zamknutý plán. Presne
      --     na to prvý beh tejto migrácie narazil. Slot ostáva zdvihnutý aj pre
      --     bod (3), takže `free` už môže padnúť jedine na RLS.
      update accounts
         set plan = 'vip_lite',
             model_slots = (select count(*) from models where account_id = v_probe) + 1
       where id = v_probe;
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe, 'role', 'authenticated')::text, true);
      begin
        execute 'set local role authenticated';
        begin
          insert into models (account_id, name) values (v_probe, 'viplite-probe');
          v_lite_moze := true;
        exception when others then
          v_lite_moze := false;
          -- Dôvod si necháme: „nesmie založiť modelku" bez neho neodlíši
          -- zamknutý plán od vyčerpaného slotu či iného triggeru.
          v_preco := sqlerrm;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
        raise;
      end;

      -- (3) A `free` NESMIE — slot je stále voľný, takže jediné, čo ho môže
      --     zastaviť, je zámok.
      update accounts set plan = 'free' where id = v_probe;
      begin
        execute 'set local role authenticated';
        begin
          insert into models (account_id, name) values (v_probe, 'viplite-probe-free');
        exception when others then v_free_blokovany := true;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
        raise;
      end;

      v_reached := true;
      raise exception 'viplite-unlock-probe-rollback';
    exception when others then
      if sqlerrm <> 'viplite-unlock-probe-rollback' then raise; end if;
    end;

    perform set_config('request.jwt.claims', '', true);
    update accounts set role = v_role_before, plan = v_plan_before where id = v_probe;

    if not v_reached then
      raise exception 'viplite-unlock: sonda nedobehla';
    end if;
    if array_length(v_zamknute, 1) is not null then
      raise exception 'viplite-unlock: plán(y) % sú zamknuté, hoci nie sú free', v_zamknute;
    end if;
    if v_free_odomknute then
      raise exception 'viplite-unlock: plán free je odomknutý — zámok je preč';
    end if;
    if not v_lite_moze then
      raise exception 'viplite-unlock: vip_lite nesmie založiť modelku (%)', v_preco;
    end if;
    if not v_free_blokovany then
      raise exception 'viplite-unlock: free účet založil modelku — zámok netesní';
    end if;
  end if;

  raise notice 'vip_lite je odomknutý — OK';
end $$;

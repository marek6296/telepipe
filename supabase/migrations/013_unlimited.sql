-- Neobmedzené účty — superadmin (a interné účty) sa nikdy neblokujú.
--
-- Princíp: `unlimited` NEVYPÍNA meranie. Každé volanie sa aj naďalej zapíše do
-- `usage_events` (admin tak vidí reálnu spotrebu aj maržu), len sa neodpočíta
-- z `credit_balance_usd` a MeteredLlm nad takým účtom nekontroluje zostatok.
-- Opak (nezapisovať usage) by znamenal, že vlastná prevádzka zmizne z čísel.

-- ---------------------------------------------------------------------------
-- (a) accounts.unlimited
-- ---------------------------------------------------------------------------

alter table accounts add column unlimited boolean not null default false;

-- Marek — jediný superadmin, jeho modelky (Simona, Mio) bežia bez kreditu.
update accounts set unlimited = true where email = 'cmelo.marek@gmail.com';

-- `accounts` má z 007 tabuľkový `grant select` pre authenticated, ktorý nové
-- stĺpce pokrýva automaticky; explicitný stĺpcový grant je tu pre čitateľnosť
-- auditu (rovnako ako role/plan v 009). Zápis klient nemá — príznak mení
-- výhradne superadmin cez `admin_set_unlimited()` nižšie.
grant select (unlimited) on accounts to authenticated;

-- ---------------------------------------------------------------------------
-- (b) credit_state — zostatok + príznak v jednom kole (worker)
-- ---------------------------------------------------------------------------

-- MeteredLlm potrebuje pred každým volaním oboje. Dve RPC = dva round-tripy na
-- každú správu, preto jedno. `credit_balance()` zostáva kvôli spätnej
-- kompatibilite (starší worker počas rolloutu, integračné testy).
create or replace function credit_state(p_model uuid)
returns table (balance numeric, unlimited boolean)
language sql stable security definer
set search_path = public, pg_temp as $$
  select a.credit_balance_usd, a.unlimited
  from accounts a join models m on m.account_id = a.id
  where m.id = p_model;
$$;

-- Rovnaký režim ako credit_balance: číta výhradne worker cez service_role.
revoke execute on function credit_state(uuid) from public, anon, authenticated;
grant execute on function credit_state(uuid) to service_role;

-- ---------------------------------------------------------------------------
-- (c) record_usage — ledger vždy, odpočet len obmedzeným účtom
-- ---------------------------------------------------------------------------

-- POZOR: `create or replace` prepisuje aj atribúty funkcie, takže pripnutý
-- search_path z 002 sa musí zopakovať tu (inak by zmizol). Grants ostávajú.
create or replace function record_usage(
  p_model uuid, p_kind text,
  p_input_tokens int, p_output_tokens int, p_unit_count int,
  p_atlas_cost_usd numeric, p_charged_usd numeric
) returns numeric language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_account uuid; v_unlimited boolean; v_balance numeric;
begin
  select account_id into v_account from models where id = p_model;

  -- Ledger prvý a bez podmienky — spotreba neobmedzeného účtu je stále náklad
  -- a musí byť v admin prehľadoch vidieť.
  insert into usage_events (model_id, account_id, kind, input_tokens,
    output_tokens, unit_count, atlas_cost_usd, charged_usd)
  values (p_model, v_account, p_kind, p_input_tokens, p_output_tokens,
    p_unit_count, p_atlas_cost_usd, p_charged_usd);

  select a.credit_balance_usd, a.unlimited into v_balance, v_unlimited
  from accounts a where a.id = v_account;

  if not coalesce(v_unlimited, false) then
    update accounts set credit_balance_usd = credit_balance_usd - p_charged_usd
    where id = v_account
    returning credit_balance_usd into v_balance;
  end if;

  -- Vždy aktuálny zostatok (pri unlimited nezmenený) — volajúci si ho loguje.
  return v_balance;
end;
$$;

-- ---------------------------------------------------------------------------
-- (d) admin_set_unlimited — prepínač len pre superadmina
-- ---------------------------------------------------------------------------

-- Rovnaká váha ako zmena roly: kto sa dostane k `unlimited`, míňa bez limitu.
-- Preto `is_superadmin()`, nie `is_admin()`. Audit ide do `credit_adjustments`
-- (amount 0 — peniazmi to nehýbe, ale kto to kedy zapol musí byť dohľadateľné).
create or replace function admin_set_unlimited(p_account uuid, p_value boolean)
returns boolean language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_value boolean := coalesce(p_value, false);
begin
  if not is_superadmin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if not exists (select 1 from accounts where id = p_account) then
    raise exception 'account not found';
  end if;

  insert into credit_adjustments (account_id, admin_id, amount, note)
  values (p_account, auth.uid(), 0, 'unlimited=' || v_value);

  update accounts set unlimited = v_value where id = p_account;
  return v_value;
end;
$$;

-- ---------------------------------------------------------------------------
-- (e) admin_list_accounts — príznak do admin tabuľky
-- ---------------------------------------------------------------------------

-- Návratový typ sa mení, `create or replace` to nevie — drop + create. Grants
-- padajú spolu s funkciou, preto sa nižšie prideľujú znova.
drop function if exists admin_list_accounts();

create or replace function admin_list_accounts()
returns table (
  id uuid, email text, role text, plan text, unlimited boolean,
  credit_balance_usd numeric, created_at timestamptz,
  models_count bigint, spend_30d numeric
)
language plpgsql stable security definer
set search_path = public, pg_temp as $$
#variable_conflict use_column
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;

  return query
  select a.id, a.email, a.role, a.plan, a.unlimited, a.credit_balance_usd, a.created_at,
         (select count(*) from models m where m.account_id = a.id),
         coalesce((select sum(u.charged_usd) from usage_events u
                    where u.account_id = a.id
                      and u.created_at > now() - interval '30 days'), 0)
  from accounts a
  order by a.created_at;
end;
$$;

-- ---------------------------------------------------------------------------
-- (f) Grants na admin RPC — anon nikdy, authenticated áno (rolu si overí funkcia)
-- ---------------------------------------------------------------------------

revoke execute on function admin_list_accounts() from public, anon;
revoke execute on function admin_set_unlimited(uuid, boolean) from public, anon;

grant execute on function admin_list_accounts() to authenticated;
grant execute on function admin_set_unlimited(uuid, boolean) to authenticated;

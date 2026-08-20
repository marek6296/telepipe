-- Ako dlho sa modelka s jedným človekom baví, kým stíchne.
--
-- Predtým to bolo napevno: útlm sa počítal od chvíle, keď odišiel odkaz, a
-- kto odkaz nikdy nedostal, sa neutlmil nikdy. Teraz si klient nastaví okno
-- v dňoch od prvého kontaktu; prvý deň je najaktívnejšia, potom odpisuje
-- čoraz menej a po okne už neodpíše vôbec (ani „videné"). Viď worker/src/taper.py.

alter table behavior
  add column if not exists chat_days int not null default 3;

alter table behavior drop constraint if exists behavior_chat_days_check;
alter table behavior add constraint behavior_chat_days_check
  check (chat_days between 1 and 14);

comment on column behavior.chat_days is
  'Dĺžka okna konverzácie v dňoch (1–14). Meria sa od prvého kontaktu, nie '
  'od odkazu. Po okne modelka neodpisuje ani nedáva videné.';

-- `behavior` má stĺpcové granty (nie tabuľkové), takže nový stĺpec treba
-- povoliť výslovne — inak ho klient v nastaveniach neuvidí ani nenastaví.
revoke all (chat_days) on behavior from authenticated;
grant select (chat_days), update (chat_days) on behavior to authenticated;

do $$
declare
  v_model uuid;
  v_ok boolean := false;
begin
  select model_id into v_model from behavior limit 1;
  if v_model is not null then
    begin
      update behavior set chat_days = 0 where model_id = v_model;
    exception when check_violation then v_ok := true;
    end;
    if not v_ok then
      raise exception 'chat_days: nula prešla cez CHECK';
    end if;

    v_ok := false;
    begin
      update behavior set chat_days = 15 where model_id = v_model;
    exception when check_violation then v_ok := true;
    end;
    if not v_ok then
      raise exception 'chat_days: 15 prešlo cez CHECK';
    end if;
  end if;

  if not has_column_privilege('authenticated', 'behavior', 'chat_days', 'UPDATE') then
    raise exception 'chat_days: klient to nemôže nastaviť';
  end if;
  if not has_column_privilege('authenticated', 'behavior', 'chat_days', 'SELECT') then
    raise exception 'chat_days: klient to nevidí';
  end if;

  raise notice 'behavior.chat_days OK';
end $$;

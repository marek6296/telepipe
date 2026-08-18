-- 027 — „Reset stats": čistý štart na dashboarde bez mazania účtovníctva
--
-- ČO CHCEL KLIENT: dať si čísla na nulu a sledovať modelku odznova. Rozumné —
-- prvý deň s novou modelkou je plný testovania a wizardu, a tie čísla potom
-- roky kazia priemer.
--
-- ČO SME NEUROBILI: nezmazali sme `usage_events`. Tá tabuľka je účtovný ledger
-- — je z nej naša marža, zostatok klienta aj dôkaz, za čo zaplatil. Zmazať ju
-- na kliknutie z prehliadača by znamenalo, že si klient (aj my) vieme prepísať
-- históriu peňazí. To sa nerobí.
--
-- ČO ROBÍME MIESTO TOHO: `stats_since` je hranica, od ktorej klientove vlastné
-- prehľady počítajú. Na obrazovke je výsledok ten istý (všetko na nule), riadky
-- ostávajú. Admin prehľady hranicu ignorujú — to sú NAŠE čísla.

alter table accounts add column if not exists stats_since timestamptz;

comment on column accounts.stats_since is
  'Hranica pre klientove vlastné prehľady (dashboard, usage). NULL = od začiatku. '
  'Admin pohľady ju ignorujú — usage_events sa nikdy nemaže.';

/**
 * Posunie hranicu na teraz. Vlastný účet a nič iné — `p_account` tu zámerne
 * nie je, aby sa cez toto nedalo siahnuť na cudzí účet ani omylom.
 */
create or replace function reset_my_stats()
returns timestamptz
language plpgsql
security definer
set search_path to 'public', 'pg_temp'
as $$
declare v_now timestamptz := now();
begin
  -- `accounts.id` JE id z `auth.users` (viď politiku `accounts_owner_select`),
  -- takže žiadne mapovanie netreba a cudzí účet sa sem nemá ako dostať.
  update accounts set stats_since = v_now where id = auth.uid();
  if not found then
    raise exception 'account not found';
  end if;
  return v_now;
end;
$$;

revoke all on function reset_my_stats() from public, anon;
grant execute on function reset_my_stats() to authenticated;

-- Kontrola: prihlásený ju spustiť smie, neprihlásený nie.
do $$
begin
  if not has_function_privilege('authenticated', 'reset_my_stats()', 'execute') then
    raise exception '027: authenticated nemá execute na reset_my_stats';
  end if;
  if has_function_privilege('anon', 'reset_my_stats()', 'execute') then
    raise exception '027: anon má execute na reset_my_stats';
  end if;
  if not exists (
    select 1 from information_schema.columns
     where table_name = 'accounts' and column_name = 'stats_since'
  ) then
    raise exception '027: accounts.stats_since chýba';
  end if;
end $$;

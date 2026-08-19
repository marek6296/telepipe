-- Uvítanie sa neriadi značkou „videl som to", ale skutočným stavom appky.
--
-- PREČO SA TO MENÍ HNEĎ PO 20260819230000
-- ---------------------------------------
-- Pôvodne sa okno ukázalo RAZ a zavretie sa zapísalo do
-- `accounts.onboarding_done_at`. Lenže tá značka hovorí o tom, či človek okno
-- ZAVREL — nie o tom, či má appku nastavenú. Kto ho odklikol a nič neurobil,
-- návod už nikdy nedostal, hoci ho potreboval najviac.
--
-- Odteraz visí zobrazenie na jedinej otázke: má už niektorá modelka prihlásený
-- Telegram? Kým nie, okno vyskočí pri každom príchode na dashboard; len čo áno,
-- prestane samo a natrvalo. Odpoveď sa dá prečítať z `models` a `tg_login_jobs`,
-- takže značka nie je na nič — a stĺpec, ktorý nikto nečíta, je len ďalšia vec,
-- ktorú musí niekto o rok pochopiť.
--
-- Zahadzuje sa preto celá: stĺpec aj RPC. Dáta v nej žiadne nie sú (feature má
-- pár hodín a všetky riadky sú `null`), takže sa niet o čo prísť.
--
-- ŠTARTOVACÍ KREDIT z 20260819230000 ZOSTÁVA — s uvítacím oknom súvisí len tým,
-- že ho okno spomína. Pripisuje sa ďalej pri prvom schválení.

drop function if exists mark_onboarding_done();

alter table accounts drop column if exists onboarding_done_at;

-- ---------------------------------------------------------------------------
-- Sonda
-- ---------------------------------------------------------------------------

do $$
declare
  v_kredit numeric;
begin
  -- (1) Naozaj preč — inak by v schéme ostal pojem, ktorý už nič neznamená.
  if exists (
    select 1 from information_schema.columns
     where table_schema = 'public' and table_name = 'accounts'
       and column_name = 'onboarding_done_at'
  ) then
    raise exception 'onboarding: stĺpec onboarding_done_at tu ešte je';
  end if;

  if exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'mark_onboarding_done'
  ) then
    raise exception 'onboarding: RPC mark_onboarding_done tu ešte je';
  end if;

  -- (2) A to, čo ostať MALO, ostalo. Bez tejto kontroly by sa dalo omylom
  --     stiahnuť celé 230000 aj s kreditom, ktorý s oknom nesúvisí.
  v_kredit := config_value('signup_credit_usd', -1);
  if v_kredit < 0 then
    raise exception 'onboarding: zmizol kľúč signup_credit_usd';
  end if;

  if (select pg_get_functiondef(oid) from pg_proc where proname = 'decide_access_request')
     not like '%signup credit%' then
    raise exception 'onboarding: decide_access_request už nepripisuje štartovací kredit';
  end if;

  raise notice 'onboarding: značka zahodená, štartovací kredit (%) ostáva', v_kredit;
end $$;

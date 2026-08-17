-- Korekcia pomenovania: `model_type = 'girl'` → `'persona'`.
--
-- PREČO SAMOSTATNÝ SÚBOR: 018 sa v produkcii aplikovala v prvej verzii, kde sa
-- typ volal `girl`. Meno je zle zvolené — typ opisuje SPÔSOB, akým agent píše
-- (persona, hlasovky, funnel), nie pohlavie toho, koho hrá. Firemný ani osobný
-- agent nemá s pohlavím nič spoločné a `girl` by v admin tabuľke aj v API
-- zostalo navždy. Meniť sa to má teraz, kým sú v tabuľke dva riadky.
--
-- `018_model_type.sql` je prepísaná na cieľový stav (`persona`), takže čistá DB
-- si prehrá rovno správnu verziu a táto migrácia na nej neurobí NIČ — všetky
-- kroky sú písané idempotentne. Na produkčnej DB (kde je `girl`) prevedie
-- hodnotu, default, `check` aj obe funkcie.
--
-- Dáta: mení sa výhradne `models.model_type`. Simona ani Mio nedostanú iný
-- status, meno, session ani nič ďalšie. Jediný vedľajší účinok je `updated_at`
-- — bumpne ho trigger `models_touch_updated_at_trg` (010), lebo UPDATE je
-- UPDATE. Overené diffom: všetky ostatné stĺpce oboch riadkov sedia bit po bite.

-- ---------------------------------------------------------------------------
-- (a) Povoliť `persona` skôr, než sa ňou začnú riadky prepisovať
-- ---------------------------------------------------------------------------
--
-- Poradie nie je kozmetika: `models_type_guard` (018) beží aj pri UPDATE
-- stĺpca, a kým `model_type_enabled` pozná len `girl`, každý UPDATE na
-- `persona` by skončil chybou „model type not available yet".

create or replace function model_type_enabled(p_type text)
returns boolean language sql immutable
set search_path = public, pg_temp as $$
  -- Rozšíriť, až keď pre daný typ existuje beh vo workeri aj UI.
  select p_type = 'persona';
$$;

revoke execute on function model_type_enabled(text) from public, anon;
grant execute on function model_type_enabled(text) to authenticated;

-- ---------------------------------------------------------------------------
-- (b) Hodnota, check a default
-- ---------------------------------------------------------------------------
--
-- Check sa najprv zahodí, lebo `girl` aj `persona` v ňom naraz byť nemajú —
-- prechodný stav „platia obe" je presne to, čo by tu neskôr ostalo zabudnuté.

alter table models drop constraint if exists models_type_valid;

alter table models alter column model_type set default 'persona';

update models set model_type = 'persona' where model_type = 'girl';

alter table models
  add constraint models_type_valid
  check (model_type in ('persona','business','private'));

comment on column models.model_type is
  'Typ agenta: persona (persona/hlas/funnel/Fanvue), business, private. Volí sa '
  'pri založení a nemení sa. Dnes je založiteľný len persona — viď '
  'model_type_enabled() a trigger models_type_guard.';

-- ---------------------------------------------------------------------------
-- (c) claim_models — filter musí sedieť s novou hodnotou
-- ---------------------------------------------------------------------------
--
-- Toto je najdôležitejší riadok celej migrácie: keby sa zabudol, `claim_models`
-- by hľadal `girl`, nenašiel by nič a Simona s Miom by po najbližšom heartbeate
-- prestali odpovedať. Preto je pod tým self-check, ktorý to naozaj skúša.

create or replace function claim_models(p_replica text, p_capacity int)
returns setof models language sql security definer
set search_path = public, pg_temp as $$
  update models m set claimed_by = p_replica, heartbeat_at = now()
  where m.id in (
    select id from models
    where status = 'active'
      and model_type = 'persona'
      and (claimed_by is null or heartbeat_at < now() - interval '90 seconds')
      and (claimed_by is distinct from p_replica)
    order by created_at
    for update skip locked
    limit p_capacity
  )
  returning m.*;
$$;

revoke execute on function claim_models(text, int) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- (d) Self-check
-- ---------------------------------------------------------------------------

do $$
declare v_bad int; v_src text;
begin
  select count(*) into v_bad from models where model_type <> 'persona';
  if v_bad > 0 then
    raise exception 'po premenovaní ostali modelky mimo persona (%)', v_bad;
  end if;

  if model_type_enabled('girl') or model_type_enabled('business')
     or model_type_enabled('private') then
    raise exception 'model_type_enabled pustil typ, ktorý nemá beh';
  end if;
  if not model_type_enabled('persona') then
    raise exception 'model_type_enabled odmieta persona';
  end if;

  -- Filter v claim_models sa kontroluje na zdrojáku funkcie, nie spustením —
  -- spustiť ju znamená ukradnúť lease bežiacej replike.
  select prosrc into v_src from pg_proc where proname = 'claim_models';
  if v_src is null or v_src not like '%model_type = ''persona''%' then
    raise exception 'claim_models nefiltruje na persona — worker by nenaklaimoval nič';
  end if;

  if exists (
    select 1 from pg_constraint
    where conname = 'models_type_valid' and pg_get_constraintdef(oid) like '%girl%'
  ) then
    raise exception 'models_type_valid stále pozná girl';
  end if;
end $$;

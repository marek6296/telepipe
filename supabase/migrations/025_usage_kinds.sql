-- 025 — rozdelenie `usage_events.kind`, aby „odpoveď" naozaj znamenala odpoveď
--
-- PROBLÉM: `kind='chat'` doteraz zbieralo tri rôzne veci naraz:
--   1. `llm.reply()`      — správa, ktorú modelka naozaj napísala a odoslala
--   2. `llm.structured()` — sudca, pamäťové tvrdenia, fakty, recall, hovorená
--                           forma hlasovky; beží NA POZADÍ jednej odpovede
--   3. AI wizard v appke  — persona builder a staviteľ denného rozvrhu
--
-- Dashboard z toho počíta dlaždicu „Replies sent" a graf „Messages by model",
-- takže klientovi ukazoval trojnásobok. Živý príklad, kvôli ktorému to vzniklo:
-- účet r.brodniansky@gmail.com mal na dashboarde 10 odpovedí, pričom modelka
-- odoslala jedinú — zvyšok boli dva behy wizardu a štyri pomocné volania.
--
-- RIEŠENIE: `chat` ostáva vyhradený pre skutočne odoslanú odpoveď, ostatné
-- dostávajú vlastný kind. Účtuje sa všetko rovnako ako doteraz — mení sa LEN
-- štítok, nie peniaze.
--
-- Staré riadky sa NEPREPISUJÚ. Spätne sa `reply` od `structured` rozlíšiť nedá
-- (rozdiel bol len v tom, ktorá metóda volanie spustila) a hádať v účtovnom
-- ledgeri sa nebude. Čísla sa teda vyčistia samy, ako staré riadky vypadnú
-- zo 7-dňového okna dashboardu.

alter table usage_events drop constraint if exists usage_events_kind_check;

alter table usage_events add constraint usage_events_kind_check check (
  kind in (
    'chat',     -- odoslaná odpoveď (`llm.reply`)
    'assist',   -- práca na pozadí jednej odpovede (`llm.structured`)
    'builder',  -- AI pomocník v appke: persona a denný rozvrh
    'summary',  -- prepis pamäte
    'vision',   -- pozretá fotka
    'audio',    -- prepis prijatej hlasovky
    'voice'     -- vygenerovaná hlasovka
  )
);

-- Kontrola: nové druhy musia prejsť, vymyslený nie.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'usage_events'::regclass
      and conname = 'usage_events_kind_check'
      and pg_get_constraintdef(oid) like '%assist%'
      and pg_get_constraintdef(oid) like '%builder%'
  ) then
    raise exception '025: check constraint nepozná assist/builder';
  end if;
end $$;

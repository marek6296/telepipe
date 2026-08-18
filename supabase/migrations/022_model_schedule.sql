-- Denný život modelky ako nastavenie, nie ako kód.
--
-- PREČO. `worker/src/den.py` skladá každej modelke deň: kde je o ktorej, čo
-- práve robí, ako rýchlo odtiaľ odpisuje a odkiaľ znie jej hlasovka. Bol
-- napísaný v Pythone, takže ho mali všetky modelky rovnaký a klient si ho
-- nemal kde nastaviť — pritom je to presne tá vec, ktorá z modelky robí
-- niekoho, kto žije, a nie chatbota, čo je vždy „doma".
--
-- ČO SA NEMENÍ. Losovanie ostáva vo workeri. Klient nastavuje TVAR dňa
-- (poradie činností, miesta, rozsahy trvania, okná vstávania), nie hodiny:
-- fitko od 14:00 do 15:30 je rozvrh z papiera, človek príde 14:03. Preto sú
-- trvania rozsahy a preto sa deň losuje z dvojice (modelka, dátum) — ten istý
-- deň vyjde vždy rovnako, takže si modelka o pol hodiny neprotirečí.
--
-- PREČO VLASTNÁ TABUĽKA A NIE STĹPEC V `behavior`. `behavior` je plochý zoznam
-- čísel, ktorý sa v UI aj v kontrolnom botovi posúva po jednom poli
-- (`set_behavior_field`, `saveBehaviorAction`). Rozvrh je jeden celok — zoznam,
-- ktorý sa pridáva, maže a preusporadúva; uložiť ho po poliach nejde. Vlastný
-- riadok zároveň dáva jasnú odpoveď na otázku „má táto modelka rozvrh?": worker
-- pri chýbajúcom riadku pobeží po napísanej šablóne presne ako doteraz.
--
-- PREČO SÚ ČINNOSTI JSONB A NIE RIADKY. Poradie dňa je poradie v poli. Keby bol
-- každý krok riadkom, poradie by držal stĺpec `position` a jeho prečíslovanie
-- pri každom presune je klasický zdroj dier a duplicít — navyše by sa ukladalo
-- N dotazmi tam, kde má UI jedno auto-save. Tvar poľa preto stráži CHECK nižšie,
-- nie schéma tabuľky.
--
-- GRANTY. Rovnaké pravidlo ako v 007 a 020: Supabase má nastavené `alter
-- default privileges ... grant all on tables to anon, authenticated`, takže nová
-- tabuľka dostane pri vzniku plné práva. Najprv sa preto všetko odoberie a potom
-- sa pridá len to, čo klient naozaj potrebuje.

-- ---------------------------------------------------------------------------
-- (a) Kontrola tvaru jednej činnosti
-- ---------------------------------------------------------------------------

-- Prečo plpgsql a nie jeden `not exists (...)`: podmienky sa MUSIA vyhodnotiť
-- v poradí. `(e->>'pace')::numeric` na texte nevráti `false`, ale vyhodí chybu
-- s nečitateľnou hláškou, a SQL negarantuje, že sa typová kontrola vyhodnotí
-- skôr než pretypovanie. Cyklus s `return false` to poradie garantuje.
--
-- `immutable` je nutné, aby sa funkcia dala použiť v CHECK constrainte.
create or replace function schedule_activities_ok(a jsonb)
returns boolean language plpgsql immutable
set search_path = public, pg_temp as $$
declare
  e jsonb;
  d jsonb;
  lo int;
  hi int;
begin
  if a is null or jsonb_typeof(a) <> 'array' then
    return false;
  end if;
  -- Aspoň jedna: prázdny rozvrh by znamenal modelku, ktorá od prebudenia do
  -- druhej v noci leží v posteli a o sebe nemá čo povedať. Strop je proti
  -- riadku, ktorý by sa dal nafúknuť do megabajtov.
  if jsonb_array_length(a) < 1 or jsonb_array_length(a) > 60 then
    return false;
  end if;

  for e in select value from jsonb_array_elements(a) loop
    if jsonb_typeof(e) <> 'object' then
      return false;
    end if;
    -- Miestnosť musí sedieť na `eleven.AMBIENCES` — z nej sa robí pozadie
    -- hlasovky. Neznáme meno by znamenalo ticho namiesto miestnosti.
    if coalesce(e->>'place', '') not in
       ('home', 'bedroom', 'kitchen', 'bathroom', 'car', 'outside', 'cafe', 'gym', 'none') then
      return false;
    end if;
    -- „Čo robí" ide rovno do promptu; prázdne by nechalo modelku bez odpovede
    -- na otázku, kde je.
    if coalesce(btrim(e->>'what'), '') = '' or length(e->>'what') > 200 then
      return false;
    end if;
    if length(coalesce(e->>'arrival', '')) > 200 then
      return false;
    end if;
    if jsonb_typeof(e->'pace') <> 'number'
       or (e->>'pace')::numeric < 0.1 or (e->>'pace')::numeric > 6 then
      return false;
    end if;
    if jsonb_typeof(e->'min_minutes') <> 'number'
       or jsonb_typeof(e->'max_minutes') <> 'number' then
      return false;
    end if;
    lo := (e->>'min_minutes')::numeric;
    hi := (e->>'max_minutes')::numeric;
    if lo < 5 or hi > 600 or hi < lo then
      return false;
    end if;
    if jsonb_typeof(e->'days') <> 'array' or jsonb_array_length(e->'days') < 1 then
      return false;
    end if;
    for d in select value from jsonb_array_elements(e->'days') loop
      if jsonb_typeof(d) <> 'number' or (d::text)::numeric < 0 or (d::text)::numeric > 6 then
        return false;
      end if;
    end loop;
  end loop;

  return true;
end;
$$;

-- CHECK constraint sa vyhodnocuje právami toho, KTO ZAPISUJE — nie vlastníka
-- tabuľky. Bez execute grantu by každý klientský insert aj update skončil
-- hláškou „permission denied for function schedule_activities_ok" (overené na
-- projekte). Validátor nič neprezrádza: vracia áno/nie nad dátami, ktoré
-- volajúci sám poslal.
revoke execute on function schedule_activities_ok(jsonb) from public, anon;
grant execute on function schedule_activities_ok(jsonb) to authenticated;

-- ---------------------------------------------------------------------------
-- (b) Tabuľka
-- ---------------------------------------------------------------------------

create table model_schedule (
  model_id uuid primary key references models(id) on delete cascade,

  -- Okná vstávania v minútach dňa. Cez víkend vstáva neskôr a nepravidelnejšie
  -- — je to rozsah, nie čas: presné 11:20 každý deň je budík, nie človek.
  -- Defaulty sú presne to, čo mala Simona napísané v `den.py`.
  wake_weekday_start_min smallint not null default 680,  -- 11:20
  wake_weekday_end_min   smallint not null default 765,  -- 12:45
  wake_weekend_start_min smallint not null default 760,  -- 12:40
  wake_weekend_end_min   smallint not null default 860,  -- 14:20

  -- Posledný blok dňa. Trvanie nemá — dobehne do konca aktívneho okna (02:30),
  -- lebo vtedy je najdostupnejšia a nie je kam sa ďalej presúvať.
  night_place   text not null default 'bedroom',
  night_what    text not null default 'leží v posteli a ešte sa jej nechce spať',
  night_pace    numeric(4, 2) not null default 0.6,
  night_arrival text not null default 'práve si ľahla do postele',

  -- Poradie v poli je poradie dňa. Každá položka má `days` (pondelok = 0),
  -- takže z jedného zoznamu vznikne sedem rôznych dní — a to je zámer: keď mal
  -- pondelok a streda ten istý tvar, po týždni bolo vidieť vzor.
  --
  -- Default JE napísaný deň zo `den.py`, vypísaný do dát. Vďaka tomu má nová
  -- modelka od prvej sekundy rozvrh, ktorý sa dá upraviť, nie prázdnu
  -- obrazovku. Že sa tento zoznam nerozíde s Pythonom, stráži test
  -- `worker/tests/test_den.py::TestSablona::test_migracia_022_sedi_na_sablonu`.
  activities jsonb not null default $json$[
    {"place": "kitchen", "what": "práve vstala a dáva si kávu, ešte je rozospatá", "pace": 0.8, "min_minutes": 40, "max_minutes": 75, "arrival": "práve vstala", "days": [0, 1, 2, 3, 4, 5, 6]},
    {"place": "home", "what": "chystá sa do posilňovne, balí si veci", "pace": 0.9, "min_minutes": 20, "max_minutes": 45, "arrival": "", "days": [0]},
    {"place": "gym", "what": "je v posilňovni, medzi sériami pozerá do telefónu", "pace": 2.4, "min_minutes": 65, "max_minutes": 100, "arrival": "práve dorazila do posilňovne", "days": [0]},
    {"place": "bathroom", "what": "práve prišla z posilňovne a ide sa osprchovať", "pace": 1.7, "min_minutes": 20, "max_minutes": 40, "arrival": "práve prišla z posilňovne", "days": [0]},
    {"place": "home", "what": "je doma a nič zvláštne nerobí", "pace": 0.7, "min_minutes": 40, "max_minutes": 80, "arrival": "je doma", "days": [0]},
    {"place": "kitchen", "what": "varí si niečo jednoduché na večeru", "pace": 1.1, "min_minutes": 25, "max_minutes": 50, "arrival": "práve si dala niečo na jedenie", "days": [0]},
    {"place": "home", "what": "leží na gauči a pozerá niečo v telefóne", "pace": 0.5, "min_minutes": 90, "max_minutes": 170, "arrival": "", "days": [0]},
    {"place": "bathroom", "what": "chystá sa na fotenie, robí si vlasy a mejkap", "pace": 1.4, "min_minutes": 45, "max_minutes": 80, "arrival": "", "days": [1]},
    {"place": "none", "what": "je na fotení a telefón má odložený", "pace": 4.0, "min_minutes": 110, "max_minutes": 175, "arrival": "práve prišla na fotenie", "days": [1]},
    {"place": "cafe", "what": "sedí v kaviarni po fotení a nikam sa neponáhľa", "pace": 0.9, "min_minutes": 40, "max_minutes": 70, "arrival": "práve sa usadila v kaviarni", "days": [1]},
    {"place": "car", "what": "je na ceste domov", "pace": 1.9, "min_minutes": 20, "max_minutes": 35, "arrival": "práve sadla do auta", "days": [1]},
    {"place": "kitchen", "what": "varí si niečo jednoduché na večeru", "pace": 1.1, "min_minutes": 25, "max_minutes": 50, "arrival": "práve si dala niečo na jedenie", "days": [1]},
    {"place": "home", "what": "leží na gauči a pozerá niečo v telefóne", "pace": 0.5, "min_minutes": 90, "max_minutes": 170, "arrival": "", "days": [1]},
    {"place": "outside", "what": "vybavuje veci v meste, je vonku", "pace": 1.6, "min_minutes": 50, "max_minutes": 90, "arrival": "práve vyšla von", "days": [2]},
    {"place": "gym", "what": "je v posilňovni, medzi sériami pozerá do telefónu", "pace": 2.4, "min_minutes": 65, "max_minutes": 100, "arrival": "práve dorazila do posilňovne", "days": [2]},
    {"place": "bathroom", "what": "práve prišla z posilňovne a ide sa osprchovať", "pace": 1.7, "min_minutes": 20, "max_minutes": 40, "arrival": "práve prišla z posilňovne", "days": [2]},
    {"place": "home", "what": "leží na gauči a je z toho dňa hotová", "pace": 0.6, "min_minutes": 60, "max_minutes": 110, "arrival": "práve dorazila domov", "days": [2]},
    {"place": "kitchen", "what": "varí si niečo jednoduché na večeru", "pace": 1.1, "min_minutes": 25, "max_minutes": 50, "arrival": "práve si dala niečo na jedenie", "days": [2]},
    {"place": "home", "what": "leží na gauči a pozerá niečo v telefóne", "pace": 0.5, "min_minutes": 90, "max_minutes": 170, "arrival": "", "days": [2]},
    {"place": "bathroom", "what": "chystá sa na fotenie, robí si vlasy", "pace": 1.4, "min_minutes": 40, "max_minutes": 70, "arrival": "", "days": [3]},
    {"place": "none", "what": "je na fotení a telefón má odložený", "pace": 4.0, "min_minutes": 110, "max_minutes": 175, "arrival": "práve prišla na fotenie", "days": [3]},
    {"place": "car", "what": "je na ceste od fotenia", "pace": 1.9, "min_minutes": 15, "max_minutes": 30, "arrival": "práve sadla do auta", "days": [3]},
    {"place": "cafe", "what": "sedí s kamoškou v kaviarni", "pace": 1.3, "min_minutes": 50, "max_minutes": 90, "arrival": "práve sa stretla s kamoškou", "days": [3]},
    {"place": "kitchen", "what": "varí si niečo jednoduché na večeru", "pace": 1.1, "min_minutes": 25, "max_minutes": 50, "arrival": "práve si dala niečo na jedenie", "days": [3]},
    {"place": "home", "what": "leží na gauči a pozerá niečo v telefóne", "pace": 0.5, "min_minutes": 90, "max_minutes": 170, "arrival": "", "days": [3]},
    {"place": "gym", "what": "je v posilňovni, medzi sériami pozerá do telefónu", "pace": 2.4, "min_minutes": 65, "max_minutes": 100, "arrival": "práve dorazila do posilňovne", "days": [4]},
    {"place": "bathroom", "what": "práve prišla z posilňovne a ide sa osprchovať", "pace": 1.7, "min_minutes": 20, "max_minutes": 40, "arrival": "práve prišla z posilňovne", "days": [4]},
    {"place": "bedroom", "what": "chystá sa von, vyberá si čo si oblečie", "pace": 1.0, "min_minutes": 35, "max_minutes": 65, "arrival": "práve sa začala chystať von", "days": [4]},
    {"place": "outside", "what": "je vonku s kamoškou, je tam hlučno", "pace": 2.2, "min_minutes": 130, "max_minutes": 200, "arrival": "práve prišla na miesto", "days": [4]},
    {"place": "car", "what": "je na ceste domov, je unavená", "pace": 1.8, "min_minutes": 20, "max_minutes": 35, "arrival": "práve sadla do auta", "days": [4]},
    {"place": "cafe", "what": "dala si neskoré raňajky vonku", "pace": 1.0, "min_minutes": 50, "max_minutes": 90, "arrival": "práve si sadla na raňajky", "days": [5]},
    {"place": "outside", "what": "chodí po meste, nakupuje", "pace": 1.7, "min_minutes": 90, "max_minutes": 150, "arrival": "práve vyšla do mesta", "days": [5]},
    {"place": "bathroom", "what": "je doma a chystá sa na večer", "pace": 1.2, "min_minutes": 40, "max_minutes": 70, "arrival": "práve prišla domov", "days": [5]},
    {"place": "outside", "what": "je vonku, je tam hlasno a veselo", "pace": 2.2, "min_minutes": 140, "max_minutes": 210, "arrival": "práve dorazila von", "days": [5]},
    {"place": "car", "what": "je na ceste domov", "pace": 1.8, "min_minutes": 20, "max_minutes": 35, "arrival": "práve sadla do auta", "days": [5]},
    {"place": "home", "what": "je doma v pyžame a nikam sa nechystá", "pace": 0.6, "min_minutes": 70, "max_minutes": 130, "arrival": "", "days": [6]},
    {"place": "kitchen", "what": "varí si niečo poriadne, má na to čas", "pace": 1.0, "min_minutes": 45, "max_minutes": 80, "arrival": "práve začala variť", "days": [6]},
    {"place": "home", "what": "leží na gauči a pozerá seriál", "pace": 0.5, "min_minutes": 120, "max_minutes": 200, "arrival": "práve si ľahla na gauč", "days": [6]},
    {"place": "bathroom", "what": "dala si dlhú sprchu", "pace": 1.6, "min_minutes": 20, "max_minutes": 35, "arrival": "práve išla do sprchy", "days": [6]}
  ]$json$::jsonb,

  updated_at timestamptz not null default now(),

  constraint model_schedule_wake_weekday check (
    wake_weekday_start_min between 0 and 1439
    and wake_weekday_end_min between 0 and 1439
    and wake_weekday_end_min >= wake_weekday_start_min
  ),
  constraint model_schedule_wake_weekend check (
    wake_weekend_start_min between 0 and 1439
    and wake_weekend_end_min between 0 and 1439
    and wake_weekend_end_min >= wake_weekend_start_min
  ),
  constraint model_schedule_night_place check (
    night_place in ('home', 'bedroom', 'kitchen', 'bathroom', 'car', 'outside', 'cafe', 'gym', 'none')
  ),
  constraint model_schedule_night_what check (
    btrim(night_what) <> '' and length(night_what) <= 200
  ),
  constraint model_schedule_night_arrival check (length(night_arrival) <= 200),
  constraint model_schedule_night_pace check (night_pace between 0.1 and 6),
  constraint model_schedule_activities check (schedule_activities_ok(activities))
);

-- ---------------------------------------------------------------------------
-- (c) RLS + granty
-- ---------------------------------------------------------------------------

alter table model_schedule enable row level security;

revoke all on model_schedule from anon, authenticated;

create policy model_schedule_owner_all on model_schedule
  for all to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())))
  with check (model_id in (select id from models where account_id = (select auth.uid())));

grant select (model_id, wake_weekday_start_min, wake_weekday_end_min,
              wake_weekend_start_min, wake_weekend_end_min,
              night_place, night_what, night_pace, night_arrival,
              activities, updated_at)
  on model_schedule to authenticated;
grant insert (model_id, wake_weekday_start_min, wake_weekday_end_min,
              wake_weekend_start_min, wake_weekend_end_min,
              night_place, night_what, night_pace, night_arrival,
              activities, updated_at)
  on model_schedule to authenticated;
-- `model_id` sa updatom nemení: presunúť rozvrh na cudziu modelku by policy
-- síce zastavila, ale stĺpec, ktorý sa nikdy nemá meniť, nemá mať ani grant.
grant update (wake_weekday_start_min, wake_weekday_end_min,
              wake_weekend_start_min, wake_weekend_end_min,
              night_place, night_what, night_pace, night_arrival,
              activities, updated_at)
  on model_schedule to authenticated;
-- Bez `delete`: zmazaný riadok = tichý návrat k šablóne vo workeri, čo je pre
-- klienta neviditeľná zmena chovania. Na to je `reset_model_schedule()` nižšie,
-- ktorá riadok prepíše defaultom a tým povie presne to, čo klient klikol.

-- ---------------------------------------------------------------------------
-- (d) Návrat k pôvodnému dňu
-- ---------------------------------------------------------------------------

-- Defaulty sú v schéme, nie v prehliadači — „Restore the default day" preto
-- musí prejsť cez databázu, inak by sa rovnaký deň písal na dvoch miestach.
create or replace function reset_model_schedule(p_model uuid)
returns void language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if not exists (
    select 1 from models where id = p_model and account_id = (select auth.uid())
  ) then
    raise exception 'not your model';
  end if;

  delete from model_schedule where model_id = p_model;
  insert into model_schedule (model_id) values (p_model);
end;
$$;

revoke execute on function reset_model_schedule(uuid) from public, anon;
grant execute on function reset_model_schedule(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- (e) Riadky pre existujúce aj budúce modelky
-- ---------------------------------------------------------------------------

-- Rovnaký dôvod ako v 005: worker aj web riadok len PATCHujú a PATCH na
-- neexistujúci riadok ticho nespraví nič.
create or replace function provision_model_rows()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  insert into persona        (model_id) values (new.id) on conflict do nothing;
  insert into behavior       (model_id) values (new.id) on conflict do nothing;
  insert into settings       (model_id) values (new.id) on conflict do nothing;
  insert into model_schedule (model_id) values (new.id) on conflict do nothing;
  return new;
end;
$$;

revoke execute on function provision_model_rows() from public, anon, authenticated;

-- Existujúce modelky dostanú presne ten deň, ktorý im doteraz skladal `den.py`
-- — teda dnešným rozvrhom sa im nič nemení, len ho odteraz vidia a vedia
-- upraviť. Že to naozaj vyjde blok po bloku rovnako, dokazuje
-- `scripts/seed_schedule.py --check`.
insert into model_schedule (model_id) select id from models on conflict do nothing;

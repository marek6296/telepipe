-- Dorovnanie nálezov z revízie Fázy 3.3 — štyri nezávislé veci, ktoré majú
-- spoločné len to, že sú v DB a že sa na ne prišlo naraz.
--
-- (a) fv_media.spicy_override — ostrosť je vlastnosť FOTKY, nie priečinka.
--     Doteraz o nej rozhodoval výhradne priečinok a checkbox „Explicit"
--     v dashboarde nerobil nič. Priečinok je hrubé triedenie a výnimka je
--     vždy: jedna odvážnejšia fotka v „daily" sa nesmie poslať zadarmo.
--
-- (b) models.updated_at — stĺpec existuje od 001 a nikdy sa neaktualizoval.
--     `updated_at` v tabuľke, ktorá klame, je horší než žiadny.
--
-- (c) usage_events / credit_adjustments — zmazanie účtu doteraz cascade-om
--     zmietlo aj jeho účtovnú históriu. Ledger musí prežiť účet: to, čo sme
--     komu naúčtovali, je náš záznam, nie jeho vlastníctvo.
--
-- (d) heartbeat_models — vracia, ktoré riadky naozaj obnovil. Bez toho pomalá
--     (nie mŕtva) replika po 90 s stratí lease, iná si tenanta prevezme a obe
--     bežia naraz. Dve Telethon sessions na jednom účte = presne ten scenár,
--     pred ktorým sa všade inde chránime.
--
-- POZOR na Supabase default privileges (lekcia zo 007, 011, 014, 015):
-- nový STĹPEC na existujúcej tabuľke zdedí právo, ktoré má tabuľka ako celok.
-- `fv_media` má z 015 tabuľkový `select` (nové stĺpce teda pokrýva) a
-- column-scoped `update` (nové stĺpce nepokrýva). `usage_events` má z 008
-- výhradne column-scoped `select`. Preto sa nižšie granty vymenúvajú
-- explicitne a sekcia (e) si ich sama overí cez `has_column_privilege`.

-- ===========================================================================
-- (a) fv_media.spicy_override — per-fotková ostrosť prebíja rolu priečinka
-- ===========================================================================
--
-- PREČO SAMOSTATNÝ STĹPEC A NIE `spicy`
-- `spicy` je `not null default false`, takže „nikto sa toho nedotkol" a
-- „majiteľ povedal, že to ostré NIE JE" v ňom vyzerajú rovnako. To je presne
-- ten rozdiel, na ktorom celé pravidlo stojí — bez tretieho stavu by sa
-- nedalo povedať „nechaj rozhodnúť priečinok".
--
-- ROZDELENIE ROLÍ PO TEJTO MIGRÁCII
--   `spicy_override`  výslovné rozhodnutie majiteľa. null = nerozhodnuté.
--   `spicy`           ODVODENÁ efektívna hodnota, ktorú drží trigger nižšie:
--                     coalesce(spicy_override, rola priečinka = 'nsfw').
--
-- Dashboard prepína `spicy` (015 mu na to dal grant) a nič o novom stĺpci
-- nevie. Zápis do `spicy` je jednoznačné rozhodnutie o konkrétnej fotke, takže
-- ho trigger premietne do `spicy_override` — inak by ho o riadok nižšie
-- prepísala rola priečinka a checkbox by naďalej nerobil nič.
--
-- Worker číta `spicy_override` a rolu priečinka priamo (`fvmedia.effective_spicy`)
-- podľa toho istého pravidla; `spicy` je pre dashboard, aby ukazoval, čo sa
-- naozaj stane, a nie čo si niekto klikol.

alter table fv_media
  add column if not exists spicy_override boolean;

comment on column fv_media.spicy_override is
  'Výslovné rozhodnutie o ostrosti tejto fotky. null = nikto nerozhodol, '
  'platí rola priečinka (fv_folders.role).';
comment on column fv_media.spicy is
  'ODVODENÁ efektívna ostrosť: coalesce(spicy_override, rola priečinka = nsfw). '
  'Zápis do nej sa berie ako nastavenie spicy_override (trigger 016).';

-- Backfill: `spicy = true` je jediná stopa po tom, že niekto „Explicit" naozaj
-- klikol — default je false, teda nerozlíšiteľné od „nikto sa toho nedotkol".
-- Preto sa true prenáša do override a false ostáva nerozhodnuté.
update fv_media set spicy_override = true where spicy and spicy_override is null;

create or replace function fv_media_spicy_effective()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_role text;
begin
  -- Zápis do `spicy` (dashboard) = rozhodnutie o fotke → do override.
  -- Kto zapisuje `spicy_override` priamo, tomu sa do neho nesiaha.
  if tg_op = 'UPDATE'
     and new.spicy is distinct from old.spicy
     and new.spicy_override is not distinct from old.spicy_override then
    new.spicy_override := new.spicy;
  elsif tg_op = 'INSERT' and new.spicy_override is null and new.spicy then
    new.spicy_override := true;
  end if;

  select f.role into v_role
  from fv_folders f
  where f.model_id = new.model_id and f.name = new.folder;

  new.spicy := coalesce(new.spicy_override, coalesce(v_role, '') = 'nsfw');
  return new;
end;
$$;

revoke execute on function fv_media_spicy_effective() from public, anon, authenticated;

create trigger fv_media_spicy_effective_trg
  before insert or update on fv_media
  for each row execute function public.fv_media_spicy_effective();

-- Rola priečinka je východisko pre všetky jeho fotky bez vlastného rozhodnutia,
-- takže jej zmena ich musí prepočítať. Prázdny update len prebudí trigger
-- vyššie — vzorec je na jedinom mieste.
create or replace function fv_folders_role_resync()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  update fv_media m set spicy = m.spicy
  where m.model_id = new.model_id
    and m.folder = new.name
    and m.spicy_override is null;
  return null;
end;
$$;

revoke execute on function fv_folders_role_resync() from public, anon, authenticated;

create trigger fv_folders_role_resync_trg
  after update of role on fv_folders
  for each row when (new.role is distinct from old.role)
  execute function public.fv_folders_role_resync();

-- Dorovnanie existujúcich riadkov na efektívnu hodnotu. Vzorec sa tu zámerne
-- neopakuje — dopočíta ho trigger, aby existovalo jedno jediné miesto pravdy.
update fv_media set spicy = spicy;

-- Klient smie o ostrosti rozhodnúť aj priamo (novšie UI), rovnakým column-scoped
-- grantom ako zvyšok nastavení fotky v 015. Policy `fv_media_owner_update`
-- z 015 platí ďalej — nový stĺpec nepotrebuje vlastnú.
grant update (spicy_override) on fv_media to authenticated;

-- ===========================================================================
-- (b) models.updated_at — konečne pravda
-- ===========================================================================
--
-- Stĺpec je v 001 s `default now()`, ale nikto ho odvtedy nezapísal: každý
-- update (status, session, control bot token) ho nechal na čase vzniku riadku.
--
-- Lease sa ZÁMERNE nepočíta za zmenu. `heartbeat_models` prepisuje
-- `heartbeat_at` každých 30 sekúnd každej bežiacej modelke — keby to trigger
-- bral ako úpravu, `updated_at` by bol len druhý čas heartbeatu a nepovedal by
-- nič o tom, kedy sa model naozaj menil.
--
-- `security definer` tu netreba (trigger nesiaha na cudzie tabuľky), pripnutý
-- `search_path` je napriek tomu — je to domáce pravidlo pre každú funkciu.

create or replace function models_touch_updated_at()
returns trigger language plpgsql
set search_path = public, pg_temp as $$
declare v_old models := old;
begin
  v_old.claimed_by := new.claimed_by;
  v_old.heartbeat_at := new.heartbeat_at;
  v_old.updated_at := new.updated_at;
  if new is distinct from v_old then
    new.updated_at := now();
  end if;
  return new;
end;
$$;

revoke execute on function models_touch_updated_at() from public, anon, authenticated;

create trigger models_touch_updated_at_trg
  before update on models
  for each row execute function public.models_touch_updated_at();

-- ===========================================================================
-- (c) usage_events / credit_adjustments — ledger prežije zmazanie účtu
-- ===========================================================================
--
-- `on delete cascade` na `account_id` znamenalo, že zmazaním účtu zmizla aj
-- celá história toho, čo sme mu naúčtovali. To je náš účtovný záznam, nie jeho
-- vlastníctvo — a admin súhrny (`admin_usage_summary`) by po každom odchode
-- klienta spätne ukazovali iné čísla, než ukazovali včera.
--
-- Riešenie: cudzie kľúče na `set null` (riadok osirie, ale ostane) + nemenná
-- odtlačok identity priamo v riadku. E-mail a názov modelky sa denormalizujú
-- ZÁMERNE: po zmazaní účtu ich nie je odkiaľ dopočítať a účtovný doklad, ktorý
-- neprezradí komu patril, nie je doklad.

alter table usage_events
  alter column model_id drop not null,
  alter column account_id drop not null,
  add column if not exists account_email text not null default '',
  add column if not exists model_name text not null default '';

alter table usage_events drop constraint usage_events_model_id_fkey;
alter table usage_events add constraint usage_events_model_id_fkey
  foreign key (model_id) references models(id) on delete set null;

alter table usage_events drop constraint usage_events_account_id_fkey;
alter table usage_events add constraint usage_events_account_id_fkey
  foreign key (account_id) references accounts(id) on delete set null;

comment on column usage_events.account_email is
  'Nemenná kópia e-mailu účtu v čase udalosti. Prežije zmazanie účtu (016).';
comment on column usage_events.model_name is
  'Nemenná kópia názvu modelky v čase udalosti. Prežije zmazanie modelu (016).';

update usage_events u set account_email = a.email
  from accounts a where a.id = u.account_id and u.account_email = '';
update usage_events u set model_name = m.name
  from models m where m.id = u.model_id and u.model_name = '';

-- Ten istý problém mala aj tabuľka ručných zásahov do kreditu. `admin_id` bol
-- navyše `on delete restrict`, čo históriu síce nezmazalo, ale zmazanie
-- ktoréhokoľvek admina úplne zablokovalo. S odtlačkom e-mailu je `set null`
-- lepšie oboje: účet sa dá zmazať a v audite ostane, kto to bol.
alter table credit_adjustments
  alter column account_id drop not null,
  alter column admin_id drop not null,
  add column if not exists account_email text not null default '',
  add column if not exists admin_email text not null default '';

alter table credit_adjustments drop constraint credit_adjustments_account_id_fkey;
alter table credit_adjustments add constraint credit_adjustments_account_id_fkey
  foreign key (account_id) references accounts(id) on delete set null;

alter table credit_adjustments drop constraint credit_adjustments_admin_id_fkey;
alter table credit_adjustments add constraint credit_adjustments_admin_id_fkey
  foreign key (admin_id) references accounts(id) on delete set null;

update credit_adjustments c set account_email = a.email
  from accounts a where a.id = c.account_id and c.account_email = '';
update credit_adjustments c set admin_email = a.email
  from accounts a where a.id = c.admin_id and c.admin_email = '';

-- ---------------------------------------------------------------------------
-- record_usage — odtlačok identity sa píše rovno pri udalosti
-- ---------------------------------------------------------------------------
--
-- POZOR: `create or replace` prepisuje aj atribúty funkcie, takže pripnutý
-- search_path z 002 sa musí zopakovať (rovnaká pasca ako v 013). Grants
-- ostávajú, signatúra sa nemení.

create or replace function record_usage(
  p_model uuid, p_kind text,
  p_input_tokens int, p_output_tokens int, p_unit_count int,
  p_atlas_cost_usd numeric, p_charged_usd numeric
) returns numeric language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid; v_name text; v_email text;
  v_unlimited boolean; v_balance numeric;
begin
  select m.account_id, coalesce(m.name, '') into v_account, v_name
  from models m where m.id = p_model;
  select coalesce(a.email, '') into v_email from accounts a where a.id = v_account;

  -- Ledger prvý a bez podmienky — spotreba neobmedzeného účtu je stále náklad
  -- a musí byť v admin prehľadoch vidieť.
  insert into usage_events (model_id, account_id, account_email, model_name,
    kind, input_tokens, output_tokens, unit_count, atlas_cost_usd, charged_usd)
  values (p_model, v_account, coalesce(v_email, ''), coalesce(v_name, ''),
    p_kind, p_input_tokens, p_output_tokens,
    p_unit_count, p_atlas_cost_usd, p_charged_usd);

  select a.credit_balance_usd, a.unlimited into v_balance, v_unlimited
  from accounts a where a.id = v_account;

  if not coalesce(v_unlimited, false) then
    update accounts set credit_balance_usd = credit_balance_usd - p_charged_usd
    where id = v_account
    returning credit_balance_usd into v_balance;
  end if;

  return v_balance;
end;
$$;

-- ---------------------------------------------------------------------------
-- Admin RPC, ktoré do credit_adjustments zapisujú — doplniť odtlačky
-- ---------------------------------------------------------------------------

create or replace function admin_add_credit(
  p_account uuid, p_amount numeric, p_note text default ''
) returns numeric language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_balance numeric;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_amount is null or p_amount = 0 then
    raise exception 'amount must be non-zero';
  end if;

  -- Audit prvý: keby update spadol, transakcia zoberie oboje. Kto komu koľko
  -- a prečo pridal, musí byť dohľadateľné aj po zmazaní oboch účtov (016).
  insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                  amount, note)
  values (p_account, auth.uid(),
          coalesce((select email from accounts where id = p_account), ''),
          coalesce((select email from accounts where id = auth.uid()), ''),
          p_amount, coalesce(p_note, ''));

  update accounts set credit_balance_usd = credit_balance_usd + p_amount
  where id = p_account
  returning credit_balance_usd into v_balance;

  if v_balance is null then raise exception 'account not found'; end if;
  return v_balance;
end;
$$;

create or replace function admin_set_unlimited(p_account uuid, p_value boolean)
returns boolean language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_value boolean := coalesce(p_value, false);
begin
  if not is_superadmin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if not exists (select 1 from accounts where id = p_account) then
    raise exception 'account not found';
  end if;

  insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                  amount, note)
  values (p_account, auth.uid(),
          coalesce((select email from accounts where id = p_account), ''),
          coalesce((select email from accounts where id = auth.uid()), ''),
          0, 'unlimited=' || v_value);

  update accounts set unlimited = v_value where id = p_account;
  return v_value;
end;
$$;

-- Majiteľ vidí vo svojej spotrebe aj odtlačok — je to jeho e-mail a názov jeho
-- modelky. `atlas_cost_usd` (naša marža) ostáva skrytý ako v 008.
-- `credit_adjustments` nemá granty žiadne a nedostáva ich ani teraz: audit
-- ručných zásahov číta výhradne admin cez RPC.
grant select (account_email, model_name) on usage_events to authenticated;

-- ===========================================================================
-- (d) heartbeat_models — fencing token pre worker
-- ===========================================================================
--
-- Doteraz `returns void`: replika poslala heartbeat a nedozvedela sa, či ním
-- vôbec niečo obnovila. Lease pritom expiruje po 90 s a replika, ktorá ho
-- nestihla, nemusí byť mŕtva — stačí zaseknutá sieť. `claim_models` medzitým
-- tenanta pridelí inej replike, tá spustí vlastnú Telethon session a na
-- jednom Telegram účte bežia dve. To je najrýchlejšia cesta k banu.
--
-- Preto vracia id riadkov, ktoré naozaj osviežila. Čo v odpovedi nie je, už
-- replike nepatrí a `Pool._fence` taký runner okamžite zastaví.
--
-- Návratový typ sa mení, `create or replace` to nevie — drop + create. Grants
-- padajú spolu s funkciou, preto sa nižšie prideľujú znova (rovnako ako 013
-- pri `admin_list_accounts`).

drop function if exists heartbeat_models(text);

create or replace function heartbeat_models(p_replica text)
returns setof uuid language sql security definer
set search_path = public, pg_temp as $$
  update models set heartbeat_at = now()
  where claimed_by = p_replica
  returning id;
$$;

revoke execute on function heartbeat_models(text) from public, anon, authenticated;
grant execute on function heartbeat_models(text) to service_role;

-- ===========================================================================
-- (e) Poistky — grant alebo pravidlo, ktoré unikne, musí byť chyba migrácie
-- ===========================================================================

do $$
declare col text;
begin
  -- Nový stĺpec nesmie prepašovať prístup k tomu, čo je pred klientom skryté.
  if has_column_privilege('authenticated', 'public.usage_events', 'atlas_cost_usd', 'SELECT')
     or has_column_privilege('anon', 'public.usage_events', 'atlas_cost_usd', 'SELECT') then
    raise exception 'usage_events.atlas_cost_usd je pre klienta čitateľný — marža unikla';
  end if;

  -- Ledger je záznam workera; klient doň nezapíše ani teraz.
  foreach col in array array['account_email', 'model_name', 'charged_usd'] loop
    if has_column_privilege('authenticated', 'public.usage_events', col, 'UPDATE')
       or has_column_privilege('authenticated', 'public.usage_events', col, 'INSERT') then
      raise exception 'usage_events.% smie klient zapísať — to je náš doklad', col;
    end if;
  end loop;

  -- Audit ručných zásahov ostáva neviditeľný.
  if has_column_privilege('authenticated', 'public.credit_adjustments', 'amount', 'SELECT')
     or has_column_privilege('anon', 'public.credit_adjustments', 'amount', 'SELECT') then
    raise exception 'credit_adjustments je pre klienta čitateľný — má ostať service-only';
  end if;

  -- Ostrosť fotky smie klient meniť, ostatné o nej nie (015 + nový stĺpec).
  if not has_column_privilege('authenticated', 'public.fv_media', 'spicy_override', 'UPDATE')
     or not has_column_privilege('authenticated', 'public.fv_media', 'spicy_override', 'SELECT') then
    raise exception 'fv_media.spicy_override nie je pre dashboard použiteľný';
  end if;
  if has_column_privilege('authenticated', 'public.fv_media', 'folder', 'UPDATE') then
    raise exception 'fv_media.folder je zapisovateľný klientom — to je záznam, nie nastavenie';
  end if;

  -- A napokon: to, čo celá migrácia sľubuje, musí platiť aj v praxi.
  if to_regclass('public.fv_media') is not null
     and not exists (select 1 from pg_trigger
                      where tgrelid = 'public.fv_media'::regclass
                        and tgname = 'fv_media_spicy_effective_trg') then
    raise exception 'trigger na efektívnu ostrosť nevznikol';
  end if;
  if not exists (select 1 from pg_trigger
                  where tgrelid = 'public.models'::regclass
                    and tgname = 'models_touch_updated_at_trg') then
    raise exception 'trigger na models.updated_at nevznikol';
  end if;
  if (select pg_get_function_result(oid) from pg_proc
       where proname = 'heartbeat_models'
         and pronamespace = 'public'::regnamespace) <> 'SETOF uuid' then
    raise exception 'heartbeat_models nevracia zoznam obnovených riadkov';
  end if;
end $$;

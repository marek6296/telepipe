# Access Gating — Standard+ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nový používateľ sa zaregistruje do zamknutého účtu a pracovať začne až
potom, čo Marek jeho žiadosť schváli — vo webe alebo tlačidlom v Telegrame.

**Architecture:** Tretia hodnota `free_plus` v `accounts.plan`. Skutočná hranica
je RLS `with check` na `models` INSERT, ktorá volá `account_unlocked()` —
jedinú funkciu, čo o odomknutí rozhoduje. Appka tú istú funkciu iba zrkadlí
kvôli redirectu. Žiadosti žijú v `access_requests`, rozhoduje o nich jedno
jadro `decide_access_request()` s dvomi vstupmi: web (`is_admin()`) a Telegram
webhook (service role).

**Tech Stack:** Postgres/Supabase (RLS, security-definer RPC), Next.js 16 App
Router (server actions, route handlers), Telegram Bot API.

**Spec:** `docs/superpowers/specs/2026-08-19-access-gating-standard-plus-design.md`

---

## Kontext, ktorý exekútor potrebuje vedieť

**Ako sa aplikuje migrácia.** Cez Supabase MCP `apply_migration` na projekt
`cggsyshfdjycfqrhtjld`, alebo `supabase db push`. Súbor sa VŽDY zároveň uloží do
`supabase/migrations/`, aby repo bolo zdroj pravdy.

**Konvencia migrácií v tomto repo (dodržať!).** Pozri `supabase/migrations/024_two_plans.sql`
ako vzor. Každá migrácia končí `do $$` **sondou**, ktorá skúsi zakázané ťahy na
živých dátach a na konci sa odroluje sentinel výnimkou (`raise exception
'…-rollback'` chytená vonkajším `exception when raise_exception`). Sonda, ktorá
nájde dieru, musí migráciu **zhodiť**. Komentáre v migráciách sú po slovensky.

**`create or replace function` resetuje atribúty** — pripnutý
`set search_path = public, pg_temp` sa musí zopakovať pri každom prepise. Toto
je pasca, na ktorej sa v tomto repo už párkrát zakoplo (013, 016, 021, 024).

**Web nemá test runner.** Testy sú samostatné `node scripts/*.mts` skripty
(`npm run test:coins` → `scripts/coins-test.mts`). Nové testy idú tou istou
cestou. `web/package.json` sa rozšíri o skript.

**Nikdy `select('*')`** na `models`/`accounts` — rola `authenticated` má
column-scoped granty a `*` skončí na „permission denied for column".

---

## File Structure

| Súbor | Zodpovednosť |
|---|---|
| `supabase/migrations/20260819120000_access_gating_standard_plus.sql` | plán `free_plus`, `account_unlocked()`, RLS na `models`, `admin_set_plan` |
| `supabase/migrations/20260819120100_access_requests.sql` | tabuľka `access_requests`, RLS, `request_access`, `decide_access_request` + 2 vstupy, `admin_list_access_requests` |
| `web/lib/access.ts` | čisté pravidlo „je odomknutý?" — bez `next/headers`, importovateľné aj do client komponentu |
| `web/scripts/access-test.mts` | test pravidla, spúšťaný `npm run test:access` |
| `web/lib/models.ts` | +`requireUnlocked()` (redirect, číta session) |
| `web/app/locked/page.tsx` | obrazovka zamknutého účtu — MIMO `/app` |
| `web/app/locked/layout.tsx` | minimálny shell pre `/locked` |
| `web/app/locked/actions.ts` | `requestAccessAction` |
| `web/lib/telegram-admin.ts` | Bot API klient pre Marekov súkromný bot |
| `web/app/api/telegram/admin/route.ts` | webhook pre Approve/Reject tlačidlá |
| `web/lib/access-admin.ts` | serverové čítanie žiadostí pre admin panel |
| `web/app/app/admin/requests/page.tsx` | admin záložka Requests |
| `web/components/app/admin/requests-table.tsx` | tabuľka + Approve/Reject |
| `web/app/app/admin/requests/actions.ts` | server actions pre tabuľku |

---

## Task 1: Migrácia — plán `free_plus`, `account_unlocked()`, zámok v RLS

**Files:**
- Create: `supabase/migrations/20260819120000_access_gating_standard_plus.sql`

- [ ] **Step 1: Napíš migráciu aj so sondou**

Sonda je tu „failing test" — píše sa v tom istom súbore a musí zlyhať, kým
neexistuje implementácia nad ňou. Vytvor súbor s týmto obsahom:

```sql
-- Prístup na pozvanie — tretí balík `free_plus` (v UI „Standard+").
--
-- PREČO
-- -----
-- Registrácia je otvorená, ale pracovať smie až ten, koho Marek schváli. Balík
-- je nosičom toho povolenia, lebo Marek ho spravuje v tom istom dropdowne
-- v admin paneli, kde dnes prepína Standard/VIP.
--
-- ČO SA TU ZÁMERNE NEMENÍ
-- -----------------------
-- * `record_usage` — vetví sa iba na `'vip'` (021), takže `free_plus` padne do
--   vetvy `else` a účtuje sa PRESNE ako `free` dnes. Fakturácie sa nedotýkame.
-- * Existujúce účty — Mareka odomyká rola, kamaráta plán `vip`. Žiadny presun
--   dát netreba; zámok platí len na účty vzniknuté odteraz.

-- ---------------------------------------------------------------------------
-- (a) accounts.plan — whitelist v schéme
-- ---------------------------------------------------------------------------
--
-- Meno constraintu ostáva rovnaké (konvencia z 021/024), aby sa v `pg_constraint`
-- nehromadili historické verzie.

alter table accounts drop constraint if exists accounts_plan_check;
alter table accounts
  add constraint accounts_plan_check
  check (plan in ('free', 'free_plus', 'vip'));

-- ---------------------------------------------------------------------------
-- (b) account_unlocked() — JEDINÝ zdroj pravdy o odomknutí
-- ---------------------------------------------------------------------------
--
-- Volá ju RLS aj aplikácia. Keby pravidlo žilo na dvoch miestach, raz by sa
-- rozišlo — a to tiché rozídenie by bola diera, nie chyba zobrazenia.
--
-- `security definer`, lebo `authenticated` má na `accounts` column-scoped granty
-- a RLS; funkcia musí vedieť prečítať plán aj rolu ľubovoľného účtu.

create or replace function account_unlocked(p_account uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
  select exists (
    select 1 from accounts
    where id = p_account
      and (plan in ('free_plus', 'vip') or role in ('admin', 'superadmin'))
  );
$$;

revoke execute on function account_unlocked(uuid) from public, anon;
grant execute on function account_unlocked(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- (c) Zámok — RLS na models INSERT
-- ---------------------------------------------------------------------------
--
-- TOTO je celá hranica. Každá tenant tabuľka (persona, settings, photos,
-- fanvue…) visí cez `model_id` na vlastníctve modelky, takže kto si nezaloží
-- modelku, nemá sa čoho chytiť — ani ručnou URL, ani priamym PostgREST volaním.
-- Jedna brána namiesto dvadsiatich.
--
-- SELECT/UPDATE/DELETE sa ZÁMERNE nemenia: kto už modelku má a plán mu vezmú,
-- nesmie o dáta prísť ani ich vidieť rozbité. Zamkne sa mu web (redirect), nie
-- databáza.

drop policy if exists models_owner_insert on models;
create policy models_owner_insert on models
  for insert to authenticated
  with check (
    account_id = (select auth.uid())
    and account_unlocked((select auth.uid()))
  );

-- ---------------------------------------------------------------------------
-- (d) admin_set_plan — ten istý guard, o hodnotu dlhší zoznam
-- ---------------------------------------------------------------------------
--
-- Semantika z 024 sa NEMENÍ: bežné balíky smie prepínať admin, `vip` (oboma
-- smermi) výhradne superadmin. Pribudol len `free_plus` medzi bežné.
--
-- POZOR: `create or replace` prepisuje atribúty, takže pripnutý search_path
-- z 002 sa musí zopakovať (tá istá pasca ako v 013, 016, 021 a 024).

create or replace function admin_set_plan(p_account uuid, p_plan text)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare v_current text;
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  if p_plan not in ('free', 'free_plus', 'vip') then
    raise exception 'invalid plan: %', p_plan;
  end if;

  select plan into v_current from accounts where id = p_account for update;
  if v_current is null then raise exception 'account not found'; end if;
  if v_current = p_plan then return v_current; end if;

  if (p_plan = 'vip' or v_current = 'vip') and not is_superadmin() then
    raise exception 'vip plan is superadmin-only' using errcode = '42501';
  end if;

  insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                  amount, note)
  values (p_account, auth.uid(),
          coalesce((select email from accounts where id = p_account), ''),
          coalesce((select email from accounts where id = auth.uid()), ''),
          0, 'plan=' || p_plan || ' was=' || v_current);

  update accounts set plan = p_plan where id = p_account;
  return p_plan;
end;
$$;

revoke execute on function admin_set_plan(uuid, text) from public, anon;
grant execute on function admin_set_plan(uuid, text) to authenticated;

-- ---------------------------------------------------------------------------
-- (e) Sonda — čo unikne, musí byť chyba migrácie
-- ---------------------------------------------------------------------------
--
-- Beží na existujúcom nesuperadmin a NE-VIP účte; všetko, čo zmení, sa na konci
-- zahodí sentinel výnimkou (vnútorný `begin ... exception` je implicitný
-- savepoint). Rovnaký postup ako 021/024.
--
-- Body 5 a 6 sú tu podstatné: bez nich by migrácia prešla aj s dierou v zámku.
-- RLS sa nedá overiť ako postgres (vlastník tabuľky ju obchádza), preto sa na
-- ten jediný pokus prepíname cez `set local role authenticated`.

do $$
declare
  v_probe uuid;
  v_role_before text; v_plan_before text;
  v_audit_before bigint;
  v_super uuid;
  v_locked_blocked boolean := false;
  v_unlocked_ok boolean := false;
  v_unlocked_free_plus boolean := false;
  v_unlocked_free boolean := true;
  v_unlocked_vip boolean := false;
  v_unlocked_admin boolean := false;
  v_plus_ok boolean := false;
  v_vip_blocked boolean := false;
  v_dead_blocked boolean := false;
  v_check_blocks boolean := false;
  v_rec oid;
  v_reached boolean := false;
begin
  -- (0) Invariant, na ktorom stojí CELÝ návrh: `record_usage` vetví iba na
  --     'vip'. Vďaka tomu padne `free_plus` do vetvy `else` a účtuje sa presne
  --     ako `free`. Keby niekto pridal vetvu na iný plán, Standard+ by sa začal
  --     účtovať inak než Standard a nikto by si toho nevšimol — preto to
  --     kontrolujeme štrukturálne, nie behom fakturácie.
  select p.oid into v_rec from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'record_usage' limit 1;
  if v_rec is null then
    raise exception 'access-gating: record_usage neexistuje';
  end if;
  if pg_get_functiondef(v_rec) not like '%''vip''%' then
    raise exception 'access-gating: record_usage už nevetví na vip — over účtovanie free_plus';
  end if;
  if pg_get_functiondef(v_rec) like '%free_plus%' then
    raise exception 'access-gating: record_usage vetví na free_plus — Standard+ sa účtuje inak než Standard';
  end if;

  select id, role, plan into v_probe, v_role_before, v_plan_before
  from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;
  select id into v_super from accounts where role = 'superadmin' order by created_at limit 1;
  select count(*) into v_audit_before from credit_adjustments;

  if v_probe is null or v_super is null then
    raise notice 'access-gating: sonda preskočená — chýba vhodný nesuperadmin alebo superadmin účet';
  else
    begin
      -- (1) account_unlocked() na všetkých štyroch stavoch
      update accounts set role = 'user', plan = 'free' where id = v_probe;
      v_unlocked_free := account_unlocked(v_probe);

      update accounts set plan = 'free_plus' where id = v_probe;
      v_unlocked_free_plus := account_unlocked(v_probe);

      update accounts set plan = 'vip' where id = v_probe;
      v_unlocked_vip := account_unlocked(v_probe);

      update accounts set plan = 'free', role = 'admin' where id = v_probe;
      v_unlocked_admin := account_unlocked(v_probe);

      -- (2) RLS: zamknutý účet NESMIE založiť modelku
      update accounts set role = 'user', plan = 'free' where id = v_probe;
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe, 'role', 'authenticated')::text, true);
      begin
        execute 'set local role authenticated';
        begin
          insert into models (account_id, name) values (v_probe, 'access-probe-locked');
        exception when others then v_locked_blocked := true;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
      end;

      -- (3) RLS: odomknutý účet cez tú istú cestu PREJDE
      update accounts set plan = 'free_plus' where id = v_probe;
      begin
        execute 'set local role authenticated';
        begin
          insert into models (account_id, name) values (v_probe, 'access-probe-unlocked');
          v_unlocked_ok := true;
        exception when others then v_unlocked_ok := false;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
      end;

      -- (4) admin_set_plan: free_plus je bežný balík, vip ostáva superadmin-only
      update accounts set role = 'admin', plan = 'free' where id = v_probe;
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        v_plus_ok := admin_set_plan(v_probe, 'free_plus') = 'free_plus';
      exception when others then v_plus_ok := false;
      end;
      begin
        perform admin_set_plan(v_probe, 'vip');
      exception when insufficient_privilege then v_vip_blocked := true;
      end;
      begin
        perform admin_set_plan(v_probe, 'pro');
      exception when others then v_dead_blocked := true;
      end;

      -- (5) Constraint musí mŕtvy balík zastaviť aj mimo RPC
      begin
        update accounts set plan = 'pro' where id = v_probe;
      exception when check_violation then v_check_blocks := true;
      end;

      v_reached := true;
      raise exception 'access-gating-sonda-rollback' using errcode = 'P0001';
    exception when raise_exception then
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then raise exception 'access-gating: sonda spadla skôr, než dobehla'; end if;
    if v_unlocked_free then raise exception 'access-gating: free účet sa tvári ako odomknutý'; end if;
    if not v_unlocked_free_plus then raise exception 'access-gating: free_plus nie je odomknutý'; end if;
    if not v_unlocked_vip then raise exception 'access-gating: vip nie je odomknutý'; end if;
    if not v_unlocked_admin then raise exception 'access-gating: admin rola neodomyká'; end if;
    if not v_locked_blocked then raise exception 'access-gating: ZAMKNUTÝ ÚČET ZALOŽIL MODELKU — zámok je deravý'; end if;
    if not v_unlocked_ok then raise exception 'access-gating: odomknutý účet nedokázal založiť modelku'; end if;
    if not v_plus_ok then raise exception 'access-gating: admin nedokázal nastaviť free_plus'; end if;
    if not v_vip_blocked then raise exception 'access-gating: admin (nie superadmin) dokázal nastaviť vip'; end if;
    if not v_dead_blocked then raise exception 'access-gating: admin_set_plan pustil mŕtvy balík pro'; end if;
    if not v_check_blocks then raise exception 'access-gating: accounts_plan_check pustil pro'; end if;

    -- Dôkaz upratania
    if exists (
      select 1 from accounts
      where id = v_probe and (role <> v_role_before or plan <> v_plan_before)
    ) then
      raise exception 'access-gating: sonda po sebe nechala zmenený účet %', v_probe;
    end if;
    if (select count(*) from credit_adjustments) <> v_audit_before then
      raise exception 'access-gating: sonda po sebe nechala riadky v credit_adjustments';
    end if;
    if exists (select 1 from models where name like 'access-probe-%') then
      raise exception 'access-gating: sonda po sebe nechala testovacie modelky';
    end if;
  end if;
end $$;
```

- [ ] **Step 2: Over, že sonda naozaj chytá dieru (dôkaz, že test funguje)**

Predtým, než migráciu pustíš naostro, dočasne pokaz zámok — v časti (c) zmaž
riadok `and account_unlocked((select auth.uid()))` a migráciu pusti.

Run: `apply_migration` s pokazenou verziou
Expected: FAIL s `access-gating: ZAMKNUTÝ ÚČET ZALOŽIL MODELKU — zámok je deravý`

Ak prejde, sonda je nanič — oprav ju skôr, než pokračuješ.

- [ ] **Step 3: Vráť riadok späť a pusti migráciu naostro**

Run: `apply_migration` s plným súborom
Expected: SUCCESS, bez `raise notice` o preskočenej sonde

- [ ] **Step 4: Over stav v DB**

```sql
select conname, pg_get_constraintdef(oid) from pg_constraint
where conrelid = 'public.accounts'::regclass and conname = 'accounts_plan_check';

select polname, pg_get_expr(polwithcheck, polrelid) from pg_policy
where polrelid = 'public.models'::regclass and polname = 'models_owner_insert';
```

Expected: constraint obsahuje `free_plus`; policy obsahuje `account_unlocked`

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260819120000_access_gating_standard_plus.sql
git commit -m "feat(db): balík Standard+ a zámok prístupu v RLS"
```

---

## Task 2: Migrácia — `access_requests` a rozhodovanie

**Files:**
- Create: `supabase/migrations/20260819120100_access_requests.sql`

- [ ] **Step 1: Napíš migráciu aj so sondou**

```sql
-- Žiadosti o prístup — fronta, ktorú Marek odbavuje z webu alebo z Telegramu.
--
-- ROZHODOVANIE MÁ JEDNO JADRO
-- ---------------------------
-- `decide_access_request(...)` robí prácu a berie herca ako parameter. Nad ním
-- sú dva vstupy:
--   * web      → `admin_decide_access_request(...)`, autorizuje `is_admin()`
--   * Telegram → jadro priamo, service_role (v HTTP requeste žiadny auth.uid()
--                neexistuje, takže `is_admin()` by tam vždy padlo)
-- Keby mal každý vstup vlastnú kópiu logiky, raz by sa rozišli — a to by
-- znamenalo, že jednou cestou sa schvaľuje inak než druhou.

create table if not exists access_requests (
  id           uuid primary key default gen_random_uuid(),
  account_id   uuid not null references accounts(id) on delete cascade,
  status       text not null default 'pending'
               check (status in ('pending', 'approved', 'rejected')),
  message      text not null default '',
  created_at   timestamptz not null default now(),
  decided_at   timestamptz,
  decided_by   uuid references accounts(id) on delete set null,
  decided_note text not null default ''
);

-- Jeden účet = najviac jedna otvorená žiadosť. Partial index, lebo zamietnutú
-- žiadosť smie podať znova (cooldown zámerne nerobíme — pri desiatkach
-- používateľov je to problém, ktorý neexistuje).
create unique index if not exists access_requests_one_pending
  on access_requests (account_id) where status = 'pending';

create index if not exists access_requests_pending_first
  on access_requests (created_at desc) where status = 'pending';

-- ---------------------------------------------------------------------------
-- RLS — žiadateľ vidí svoje, píše výhradne RPC
-- ---------------------------------------------------------------------------

alter table access_requests enable row level security;
revoke all on access_requests from anon, authenticated;
grant select (id, account_id, status, message, created_at, decided_at, decided_note)
  on access_requests to authenticated;

create policy access_requests_owner_select on access_requests
  for select to authenticated using (account_id = (select auth.uid()));

-- Žiadny INSERT/UPDATE/DELETE policy zámerne: keby si žiadateľ vedel zapísať
-- riadok sám, vedel by si doň napísať `status = 'approved'`.

-- ---------------------------------------------------------------------------
-- request_access — žiadateľ o seba
-- ---------------------------------------------------------------------------
--
-- Idempotentné: opakovaný klik vráti existujúcu otvorenú žiadosť namiesto toho,
-- aby Marekovi nasypal do Telegramu desať správ.

create or replace function request_access(p_message text)
returns uuid language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid := auth.uid();
  v_id uuid;
begin
  if v_account is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  if account_unlocked(v_account) then
    raise exception 'account already unlocked' using errcode = '22023';
  end if;

  select id into v_id from access_requests
   where account_id = v_account and status = 'pending' limit 1;
  if v_id is not null then return v_id; end if;

  insert into access_requests (account_id, message)
  values (v_account, left(coalesce(p_message, ''), 1000))
  returning id into v_id;
  return v_id;
end;
$$;

revoke execute on function request_access(text) from public, anon;
grant execute on function request_access(text) to authenticated;

-- ---------------------------------------------------------------------------
-- decide_access_request — jadro (service_role only)
-- ---------------------------------------------------------------------------
--
-- `p_actor` je admin, ktorý rozhodol — do auditu. Schválenie dvíha plán len
-- z `free`: keby žiadosť náhodou visela účtu, ktorý medzitým dostal `vip`,
-- schválenie by ho nesmelo degradovať.

create or replace function decide_access_request(
  p_id uuid, p_approve boolean, p_note text, p_actor uuid
)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_account uuid; v_status text; v_next text;
begin
  select account_id, status into v_account, v_status
    from access_requests where id = p_id for update;
  if v_account is null then raise exception 'request not found'; end if;

  -- Už rozhodnutá žiadosť sa nerozhoduje druhýkrát. Vraciame stav, nie chybu:
  -- Marek môže kliknúť vo webe aj v Telegrame a druhý klik nemá kričať.
  if v_status <> 'pending' then return v_status; end if;

  v_next := case when p_approve then 'approved' else 'rejected' end;

  update access_requests
     set status = v_next,
         decided_at = now(),
         decided_by = p_actor,
         decided_note = left(coalesce(p_note, ''), 500)
   where id = p_id;

  if p_approve then
    insert into credit_adjustments (account_id, admin_id, account_email, admin_email,
                                    amount, note)
    values (v_account, p_actor,
            coalesce((select email from accounts where id = v_account), ''),
            coalesce((select email from accounts where id = p_actor), ''),
            0, 'access approved → plan=free_plus');
    update accounts set plan = 'free_plus' where id = v_account and plan = 'free';
  end if;

  return v_next;
end;
$$;

revoke execute on function decide_access_request(uuid, boolean, text, uuid)
  from public, anon, authenticated;
grant execute on function decide_access_request(uuid, boolean, text, uuid) to service_role;

-- ---------------------------------------------------------------------------
-- admin_decide_access_request — webový vstup do jadra
-- ---------------------------------------------------------------------------

create or replace function admin_decide_access_request(
  p_id uuid, p_approve boolean, p_note text default ''
)
returns text language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  return decide_access_request(p_id, p_approve, p_note, auth.uid());
end;
$$;

revoke execute on function admin_decide_access_request(uuid, boolean, text) from public, anon;
grant execute on function admin_decide_access_request(uuid, boolean, text) to authenticated;

-- ---------------------------------------------------------------------------
-- admin_list_access_requests — pre admin panel
-- ---------------------------------------------------------------------------

create or replace function admin_list_access_requests()
returns table (
  id uuid, account_id uuid, email text, plan text, status text, message text,
  created_at timestamptz, decided_at timestamptz, decided_note text,
  decided_by_email text
)
language sql stable security definer
set search_path = public, pg_temp as $$
  select r.id, r.account_id, a.email, a.plan, r.status, r.message,
         r.created_at, r.decided_at, r.decided_note,
         d.email as decided_by_email
  from access_requests r
  join accounts a on a.id = r.account_id
  left join accounts d on d.id = r.decided_by
  where is_admin()
  order by (r.status = 'pending') desc, r.created_at desc
  limit 500;
$$;

revoke execute on function admin_list_access_requests() from public, anon;
grant execute on function admin_list_access_requests() to authenticated;

-- ---------------------------------------------------------------------------
-- Sonda
-- ---------------------------------------------------------------------------

do $$
declare
  v_probe uuid; v_super uuid;
  v_role_before text; v_plan_before text;
  v_req uuid; v_req2 uuid;
  v_audit_before bigint; v_reqs_before bigint;
  v_idempotent boolean := false;
  v_unlocked_refused boolean := false;
  v_plan_after text;
  v_second text;
  v_direct_write_blocked boolean := false;
  v_nonadmin_blocked boolean := false;
  v_reached boolean := false;
begin
  select id, role, plan into v_probe, v_role_before, v_plan_before
  from accounts where role <> 'superadmin' and plan <> 'vip' order by created_at limit 1;
  select id into v_super from accounts where role = 'superadmin' order by created_at limit 1;
  select count(*) into v_audit_before from credit_adjustments;
  select count(*) into v_reqs_before from access_requests;

  if v_probe is null or v_super is null then
    raise notice 'access-requests: sonda preskočená — chýba vhodný účet';
  else
    begin
      update accounts set role = 'user', plan = 'free' where id = v_probe;

      -- (1) Žiadosť + idempotencia
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      v_req := request_access('prosím o prístup');
      v_req2 := request_access('druhý klik');
      v_idempotent := (v_req = v_req2);

      -- (2) Žiadateľ si NESMIE prepísať status priamo
      begin
        execute 'set local role authenticated';
        begin
          update access_requests set status = 'approved' where id = v_req;
          if not found then v_direct_write_blocked := true; end if;
        exception when others then v_direct_write_blocked := true;
        end;
        execute 'reset role';
      exception when others then
        execute 'reset role';
      end;

      -- (3) Neadmin nesmie rozhodnúť
      begin
        perform admin_decide_access_request(v_req, true, '');
      exception when insufficient_privilege then v_nonadmin_blocked := true;
      end;

      -- (4) Superadmin schváli → plán vyskočí na free_plus
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_super)::text, true);
      perform admin_decide_access_request(v_req, true, '');
      select plan into v_plan_after from accounts where id = v_probe;

      -- (5) Druhé rozhodnutie tej istej žiadosti nemá nič meniť
      v_second := admin_decide_access_request(v_req, false, 'znova');

      -- (6) Odomknutý účet už nesmie žiadať
      perform set_config('request.jwt.claims',
                         json_build_object('sub', v_probe)::text, true);
      begin
        perform request_access('ešte raz');
      exception when others then v_unlocked_refused := true;
      end;

      v_reached := true;
      raise exception 'access-requests-sonda-rollback' using errcode = 'P0001';
    exception when raise_exception then
      null;
    end;

    perform set_config('request.jwt.claims', '', true);

    if not v_reached then raise exception 'access-requests: sonda spadla skôr, než dobehla'; end if;
    if not v_idempotent then raise exception 'access-requests: druhý klik založil druhú žiadosť'; end if;
    if not v_direct_write_blocked then raise exception 'access-requests: ŽIADATEĽ SI SÁM SCHVÁLIL ŽIADOSŤ'; end if;
    if not v_nonadmin_blocked then raise exception 'access-requests: neadmin dokázal rozhodnúť'; end if;
    if v_plan_after <> 'free_plus' then raise exception 'access-requests: schválenie nedvihlo plán (je %)', v_plan_after; end if;
    if v_second <> 'approved' then raise exception 'access-requests: druhé rozhodnutie prepísalo prvé (%)', v_second; end if;
    if not v_unlocked_refused then raise exception 'access-requests: odomknutý účet dokázal požiadať znova'; end if;

    if (select count(*) from access_requests) <> v_reqs_before then
      raise exception 'access-requests: sonda po sebe nechala žiadosti';
    end if;
    if (select count(*) from credit_adjustments) <> v_audit_before then
      raise exception 'access-requests: sonda po sebe nechala audit riadky';
    end if;
    if exists (
      select 1 from accounts
      where id = v_probe and (role <> v_role_before or plan <> v_plan_before)
    ) then
      raise exception 'access-requests: sonda po sebe nechala zmenený účet';
    end if;
  end if;
end $$;
```

- [ ] **Step 2: Over, že sonda chytá dieru**

Dočasne pridaj `grant update (status) on access_requests to authenticated;` za
grant v RLS sekcii a pusti migráciu.

Run: `apply_migration` s pokazenou verziou
Expected: FAIL s `access-requests: ŽIADATEĽ SI SÁM SCHVÁLIL ŽIADOSŤ`

- [ ] **Step 3: Vráť späť a pusti naostro**

Run: `apply_migration` s plným súborom
Expected: SUCCESS

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260819120100_access_requests.sql
git commit -m "feat(db): žiadosti o prístup a ich schvaľovanie"
```

---

## Task 3: Pravidlo odomknutia vo webe + test

**Files:**
- Create: `web/lib/access.ts`
- Create: `web/scripts/access-test.mts`
- Modify: `web/lib/admin-ui.ts:20-24`, `web/lib/admin-ui.ts:57-66`
- Modify: `web/package.json` (scripts)

- [ ] **Step 1: Napíš padajúci test**

Vytvor `web/scripts/access-test.mts`:

```ts
/**
 * Test pravidla odomknutia. Beží bez DB — `isUnlocked` je čistá funkcia
 * a práve preto sa dá takto lacno otestovať.
 *
 * Spustenie: npm run test:access
 */
import assert from "node:assert/strict";

import { isUnlocked } from "../lib/access.ts";
import { PLANS, PLAN_LABEL } from "../lib/admin-ui.ts";

const cases: Array<[string, { role: string; plan: string } | null, boolean]> = [
  ["free user je zamknutý", { role: "user", plan: "free" }, false],
  ["free_plus user je odomknutý", { role: "user", plan: "free_plus" }, true],
  ["vip user je odomknutý", { role: "user", plan: "vip" }, true],
  ["admin je odomknutý aj na free", { role: "admin", plan: "free" }, true],
  ["superadmin je odomknutý aj na free", { role: "superadmin", plan: "free" }, true],
  ["neznámy plán je zamknutý", { role: "user", plan: "hacked" }, false],
  ["neznáma rola na free je zamknutá", { role: "root", plan: "free" }, false],
  ["chýbajúci účet je zamknutý", null, false],
];

for (const [name, account, expected] of cases) {
  assert.equal(isUnlocked(account), expected, name);
  console.log("  ok —", name);
}

assert.ok(PLANS.includes("free_plus" as never), "free_plus musí byť v PLANS");
assert.equal(PLAN_LABEL.free_plus, "Standard+");
assert.equal(PLANS[PLANS.length - 1], "vip", "vip musí ostať posledný");
console.log("  ok — PLANS a štítky");

console.log("access-test: OK");
```

- [ ] **Step 2: Spusti test — musí padnúť**

Run: `cd web && npm run test:access`
Expected: FAIL — skript `test:access` ešte neexistuje, potom `Cannot find module '../lib/access.ts'`

- [ ] **Step 3: Pridaj skript do `web/package.json`**

Do `"scripts"` vedľa `test:coins`:

```json
"test:access": "node scripts/access-test.mts",
```

- [ ] **Step 4: Rozšír `web/lib/admin-ui.ts`**

Nahraď blok `PLANS` (riadky 20–24):

```ts
export const PLANS = ["free", "free_plus", "vip"] as const;

/** Balíky, ktoré smie prideliť aj obyčajný admin. VIP chýba schválne —
 *  DB to strážila prvá (`admin_set_plan` → 42501), toto je len UI. */
export const ADMIN_ASSIGNABLE_PLANS = PLANS.filter((p) => p !== "vip");
```

A v komentári nad `PLANS` doplň riadok medzi `free` a `vip`:

```
 *  free_plus — schválený účet („Standard+"), účtovaný rovnako ako `free`;
 *              nesie POVOLENIE pracovať, nie inú cenu
```

Nahraď `PLAN_LABEL` a `PLAN_HINT` (riadky 57–66):

```ts
/** „Standard", nie „Free" — účet nie je zadarmo, len sa naň dokupujú coiny. */
export const PLAN_LABEL: Record<Plan, string> = {
  free: "Standard",
  free_plus: "Standard+",
  vip: "VIP",
};

/** Vysvetlenie pri balíkoch, ktoré niečo naozaj robia — aby bolo v admine hneď
 *  jasné, čo prepnutie spôsobí. */
export const PLAN_HINT: Partial<Record<Plan, string>> = {
  free: "Locked — cannot create models or buy coins until approved.",
  free_plus: "Approved — full access. Billed like Standard.",
  vip: "Billed at cost — no margin. Pipe Coins still run down.",
};
```

- [ ] **Step 5: Napíš `web/lib/access.ts`**

```ts
import { asPlan, isAdminRole, type Plan } from "@/lib/admin-ui";

/**
 * Odomknutie účtu — klientsky bezpečné zrkadlo DB funkcie `account_unlocked()`.
 *
 * POZOR: toto NIE JE hranica bezpečnosti. Skutočný zámok je RLS `with check`
 * na `models` INSERT (migrácia 20260819120000). Táto funkcia existuje preto,
 * aby appka vedela človeka presmerovať skôr, než mu databáza vráti chybu —
 * a aby sa to isté pravidlo dalo použiť aj v client komponente.
 *
 * Keď meníš pravidlo tu, MUSÍŠ ho zmeniť aj v `account_unlocked()`. Rozídenie
 * by neznamenalo rozbité UI, ale tichú dieru.
 */
export const UNLOCKED_PLANS: readonly Plan[] = ["free_plus", "vip"];

export type AccessAccount = {
  role?: string | null;
  plan?: string | null;
} | null | undefined;

export function isUnlocked(account: AccessAccount): boolean {
  if (!account) return false;
  // Admin a superadmin sú odomknutí bez ohľadu na balík — inak by si Marek
  // zamkol sám seba tým, že si prepne plán.
  if (isAdminRole(account.role)) return true;
  // `asPlan` vracia „free" pre čokoľvek neznáme, takže neznámy plán = zamknuté.
  return UNLOCKED_PLANS.includes(asPlan(account.plan));
}
```

- [ ] **Step 6: Spusti test — musí prejsť**

Run: `cd web && npm run test:access`
Expected: PASS, posledný riadok `access-test: OK`

- [ ] **Step 7: Typecheck**

Run: `cd web && npm run typecheck`
Expected: bez chýb

- [ ] **Step 8: Commit**

```bash
git add web/lib/access.ts web/lib/admin-ui.ts web/scripts/access-test.mts web/package.json
git commit -m "feat(web): pravidlo odomknutia účtu a balík Standard+"
```

---

## Task 4: Obrazovka `/locked` a redirect z `/app`

**Files:**
- Modify: `web/lib/models.ts` (pridať `requireUnlocked`)
- Modify: `web/app/app/layout.tsx:24-44`
- Create: `web/app/locked/layout.tsx`
- Create: `web/app/locked/page.tsx`
- Create: `web/app/locked/actions.ts`

- [ ] **Step 1: Pridaj `requireUnlocked` do `web/lib/models.ts`**

Za `requireUser` (riadok 84) vlož:

```ts
/**
 * Odomknutý účet, inak redirect na `/locked`.
 *
 * `/locked` je ZÁMERNE mimo `/app`: keby bola pod ním, layout `/app` by
 * redirectoval sám do seba a vznikla by slučka — a zamknutý človek by videl
 * workspace sidebar, ktorý aj tak nesmie použiť.
 */
export async function requireUnlocked(): Promise<AccountRow> {
  const account = await getAccount();
  if (!account) redirect("/login");
  if (!isUnlocked(account)) redirect("/locked");
  return account;
}
```

A hore doplň import:

```ts
import { isUnlocked } from "@/lib/access";
```

- [ ] **Step 2: Uprav `web/app/app/layout.tsx`**

Nahraď telo funkcie (riadky 24–44):

```tsx
export default async function AppLayout({ children }: LayoutProps<"/app">) {
  // Auth, účet aj sidebar sú od seba nezávislé a RLS chráni oba dátové dotazy.
  // Spustíme ich naraz, aby layout nevytváral sekvenčný waterfall.
  const [user, account, models] = await Promise.all([getUser(), getAccount(), listModels()]);
  if (!user) redirect("/login");

  // Zamknutý účet nemá v `/app` čo hľadať. Skutočný zámok je v RLS — toto je
  // len to, aby na neho nenarazil ako na chybu.
  if (!isUnlocked(account)) redirect("/locked");

  return (
    <AppShell
      email={account?.email ?? user.email ?? "your account"}
      creditBalance={toNumber(account?.credit_balance_usd)}
      isAdmin={isAdminRole(account?.role)}
      models={models.map((model) => ({
        id: model.id,
        name: model.name,
        status: model.status,
      }))}
    >
      {children}
    </AppShell>
  );
}
```

A doplň import:

```tsx
import { isUnlocked } from "@/lib/access";
```

- [ ] **Step 3: Vytvor `web/app/locked/layout.tsx`**

```tsx
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Awaiting approval",
  robots: { index: false, follow: false, noarchive: true, nocache: true },
};

/** Vlastný minimálny shell — žiadny sidebar, žiadna workspace navigácia. */
export default function LockedLayout({ children }: LayoutProps<"/locked">) {
  return (
    <div className="min-h-dvh bg-[var(--app-bg)] px-5 py-16 text-[var(--app-text)]">
      <div className="mx-auto w-full max-w-lg">{children}</div>
    </div>
  );
}
```

- [ ] **Step 4: Vytvor `web/app/locked/actions.ts`**

```ts
"use server";

import { revalidatePath } from "next/cache";

import { requireUser } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import { notifyAccessRequest } from "@/lib/telegram-admin";

export type ActionResult = { error?: string; ok?: boolean };

/**
 * Žiadosť o prístup. RPC je idempotentná, takže opakovaný klik nezaloží druhú
 * žiadosť ani nepošle Marekovi druhú správu do Telegramu.
 */
export async function requestAccessAction(
  _prev: ActionResult | undefined,
  formData: FormData,
): Promise<ActionResult> {
  const user = await requireUser();
  const message = String(formData.get("message") ?? "").trim().slice(0, 1000);

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("request_access", { p_message: message });

  if (error) {
    if (error.message.includes("already unlocked")) {
      return { error: "Your account is already active — reload the page." };
    }
    return { error: "Could not send your request. Please try again." };
  }

  // Telegram je DORUČOVACIA CESTA, nie stav. Keď spadne, žiadosť aj tak stojí
  // v admin paneli — preto sa jej chyba nesmie dostať k žiadateľovi.
  await notifyAccessRequest({
    requestId: String(data),
    email: user.email ?? "",
    message,
  });

  revalidatePath("/locked");
  return { ok: true };
}
```

- [ ] **Step 5: Vytvor `web/app/locked/page.tsx`**

```tsx
import { redirect } from "next/navigation";

import { RequestAccessForm } from "@/components/app/request-access-form";
import { isUnlocked } from "@/lib/access";
import { getAccount } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

type RequestRow = {
  status: string;
  created_at: string;
  decided_note: string;
};

export default async function LockedPage() {
  const account = await getAccount();
  if (!account) redirect("/login");
  // Odomknutý sem nemá čo pozerať — inak by mu `/locked` ostalo v histórii ako
  // strašiak.
  if (isUnlocked(account)) redirect("/app");

  const supabase = await createClient();
  const { data } = await supabase
    .from("access_requests")
    .select("status, created_at, decided_note")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const request = (data as RequestRow | null) ?? null;

  return (
    <div className="app-panel p-7">
      <p className="text-[11px] tracking-[0.14em] text-[var(--app-text-4)] uppercase">
        TelePipe
      </p>
      <h1 className="mt-3 text-[22px] font-medium">Your account is waiting for approval</h1>

      {request?.status === "pending" ? (
        <p className="mt-4 text-[14px] leading-relaxed text-[var(--app-text-2)]">
          Request sent. We review every account by hand, so this is usually hours,
          not days — you&apos;ll get an email the moment it&apos;s approved.
        </p>
      ) : request?.status === "rejected" ? (
        <>
          <p className="mt-4 text-[14px] leading-relaxed text-[var(--app-text-2)]">
            Your last request wasn&apos;t approved
            {request.decided_note ? ` — ${request.decided_note}` : "."}
          </p>
          <p className="mt-2 text-[13px] text-[var(--app-text-3)]">
            You can send another one with more detail.
          </p>
          <RequestAccessForm />
        </>
      ) : (
        <>
          <p className="mt-4 text-[14px] leading-relaxed text-[var(--app-text-2)]">
            TelePipe is invite-only while we scale. Tell us briefly what you want
            to run and we&apos;ll open your account.
          </p>
          <RequestAccessForm />
        </>
      )}

      <p className="mt-8 border-t border-[var(--app-border)] pt-5 text-[12.5px] text-[var(--app-text-4)]">
        Signed in as {account.email}
      </p>
    </div>
  );
}
```

- [ ] **Step 6: Vytvor `web/components/app/request-access-form.tsx`**

```tsx
"use client";

import { useActionState } from "react";

import { requestAccessAction } from "@/app/locked/actions";

export function RequestAccessForm() {
  const [state, formAction, pending] = useActionState(requestAccessAction, undefined);

  if (state?.ok) {
    return (
      <p className="mt-5 text-[14px] text-[var(--app-text-2)]" role="status">
        Request sent — we&apos;ll be in touch shortly.
      </p>
    );
  }

  return (
    <form action={formAction} className="mt-5 space-y-3">
      <label htmlFor="message" className="block text-[12.5px] text-[var(--app-text-3)]">
        What do you want to run? (optional)
      </label>
      <textarea
        id="message"
        name="message"
        rows={3}
        maxLength={1000}
        className="app-input w-full resize-none"
        placeholder="One Telegram persona, maybe Fanvue later…"
      />
      {state?.error && (
        <p className="text-[13px] text-[#fca5a5]" role="alert">
          {state.error}
        </p>
      )}
      <button type="submit" disabled={pending} className="app-btn app-btn-primary">
        {pending ? "Sending…" : "Request access"}
      </button>
    </form>
  );
}
```

- [ ] **Step 7: Build a typecheck**

Run: `cd web && npm run typecheck`
Expected: chyba `Cannot find module '@/lib/telegram-admin'` — to je správne, dorobí ju Task 5. Ostatné chyby oprav teraz.

- [ ] **Step 8: Commit (po Task 5, keď build prejde)**

Tento task sa commituje spolu s Task 5 — bez `telegram-admin.ts` build neprejde
a rozbitý commit sa do histórie nedáva.

---

## Task 5: Telegram klient pre Marekov súkromný bot

**Files:**
- Modify: `web/lib/env.ts` (pridať `telegramAdminBotToken`, `telegramAdminChatId`, `telegramAdminWebhookSecret`, `telegramAdminConfigured`)
- Create: `web/lib/telegram-admin.ts`

- [ ] **Step 1: Pridaj gettery do `web/lib/env.ts`**

Súbor má ustálený vzor: `export function xxx(): string` + `xxxConfigured(): boolean`
pre voliteľné integrácie (pozri `fanvueWebhookSecret` / `fanvueConfigured`,
riadky 50–61). Drž sa ho — na koniec súboru pridaj:

```ts
/* Marekov súkromný admin bot (@TelePipe_help_bot). Voliteľná integrácia:
 * keď chýba, žiadosti stále chodia do admin panelu, len sa neozve Telegram.
 * Preto `?? ""` a `telegramAdminConfigured()`, nie tvrdý throw. */
export function telegramAdminBotToken(): string {
  return process.env.TELEGRAM_ADMIN_BOT_TOKEN ?? "";
}

export function telegramAdminChatId(): string {
  return process.env.TELEGRAM_ADMIN_CHAT_ID ?? "";
}

export function telegramAdminWebhookSecret(): string {
  return process.env.TELEGRAM_ADMIN_WEBHOOK_SECRET ?? "";
}

export function telegramAdminConfigured(): boolean {
  return Boolean(telegramAdminBotToken() && telegramAdminChatId());
}
```

- [ ] **Step 2: Napíš `web/lib/telegram-admin.ts`**

```ts
import "server-only";

/**
 * Marekov SÚKROMNÝ admin bot (@TelePipe_help_bot).
 *
 * Nemá nič spoločné s control botmi modeliek vo workeri — je to samostatný bot
 * a samostatný kanál. Preto tu žiadny import z worker sveta nie je a byť nesmie.
 *
 * Odosielanie je ZÁMERNE „best effort": Telegram je doručovacia cesta, nie stav.
 * Keď spadne alebo chýba konfigurácia, žiadosť stále stojí v admin paneli.
 */

import {
  telegramAdminBotToken,
  telegramAdminChatId,
  telegramAdminConfigured,
} from "@/lib/env";

const API = "https://api.telegram.org";

function config(): { token: string; chatId: string } | null {
  if (!telegramAdminConfigured()) return null;
  return { token: telegramAdminBotToken(), chatId: telegramAdminChatId() };
}

/** Escape pre `parse_mode: HTML` — e-mail ani text od žiadateľa nesmie vedieť
 *  rozbiť správu (alebo do nej prepašovať odkaz). */
function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function call(method: string, body: unknown): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(`${API}/bot${cfg.token}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function notifyAccessRequest(input: {
  requestId: string;
  email: string;
  message: string;
}): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;

  const lines = [
    "<b>New access request</b>",
    "",
    `<b>${escapeHtml(input.email)}</b>`,
  ];
  if (input.message) lines.push("", escapeHtml(input.message));

  return call("sendMessage", {
    chat_id: cfg.chatId,
    parse_mode: "HTML",
    text: lines.join("\n"),
    reply_markup: {
      inline_keyboard: [
        [
          // `acc:ok:<uuid>` = 43 bajtov, limit callback_data je 64.
          { text: "✅ Approve", callback_data: `acc:ok:${input.requestId}` },
          { text: "✖️ Reject", callback_data: `acc:no:${input.requestId}` },
        ],
      ],
    },
  });
}

export async function answerCallback(id: string, text: string): Promise<boolean> {
  return call("answerCallbackQuery", { callback_query_id: id, text });
}

export async function editMessageText(input: {
  chatId: number | string;
  messageId: number;
  text: string;
}): Promise<boolean> {
  return call("editMessageText", {
    chat_id: input.chatId,
    message_id: input.messageId,
    parse_mode: "HTML",
    text: input.text,
  });
}
```

- [ ] **Step 3: Build**

Run: `cd web && npm run typecheck && npm run build`
Expected: PASS

- [ ] **Step 4: Commit Task 4 + 5 spolu**

```bash
git add web/lib/models.ts web/app/app/layout.tsx web/app/locked web/components/app/request-access-form.tsx web/lib/telegram-admin.ts
git commit -m "feat(web): obrazovka /locked, žiadosť o prístup a Telegram ping adminovi"
```

---

## Task 6: Zavri zvyšné dvere — model a nákup coinov

**Files:**
- Modify: `web/app/app/actions.ts:31-77` (`createModelAction`)
- Modify: `web/app/api/payments/topup/route.ts:45` (POST)

- [ ] **Step 1: Uprav `createModelAction`**

V `web/app/app/actions.ts` nahraď riadok `const user = await requireUser();`
(riadok 35) dvojicou:

```ts
  const user = await requireUser();
  // RLS to zastaví tak či tak (`models_owner_insert` → `account_unlocked`),
  // ale zamknutý človek sa sem cez UI nemá ako dostať — a keby áno, nech
  // dostane redirect, nie hlášku z databázy.
  await requireUnlocked();
```

A doplň do importu z `@/lib/models`:

```ts
import { requireUnlocked, requireUser } from "@/lib/models";
```

- [ ] **Step 2: Uprav top-up route**

V `web/app/api/payments/topup/route.ts` je `POST` na riadku 45. Nahraď riadky
46–47:

```ts
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
```

týmto:

```ts
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // Pred schválením od nikoho neberieme peniaze. Adresa depozitu vzniká cez
  // service klienta (RLS sa ho netýka), takže toto je jediné miesto, kde sa to
  // dá zastaviť — nie „pohodlie", ale skutočná brána.
  if (!isUnlocked(await getAccount())) {
    return NextResponse.json(
      { error: "Your account is not approved yet." },
      { status: 403 },
    );
  }
```

a doplň importy:

```ts
import { isUnlocked } from "@/lib/access";
import { getAccount } from "@/lib/models";
```

`GET` na riadku 127 sa nechá tak — iba číta existujúcu adresu a zamknutý účet
žiadnu nemá.

- [ ] **Step 3: Over, že iná cesta k platbe neexistuje**

Run:
```bash
cd /Users/marek/telepipe && grep -rn "grant .*on crypto" supabase/migrations/ | grep authenticated
```
Expected: iba `grant select (invoice_url) on crypto_payments to authenticated;`

Ak by sa objavil `insert`/`update` grant pre `authenticated` na ktorejkoľvek
platobnej tabuľke, tento plán ju NEZAKRÝVA — zastav sa a doplň RLS policy
s `account_unlocked()`, rovnako ako pri `models`.

- [ ] **Step 4: Build**

Run: `cd web && npm run typecheck && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/app/actions.ts web/app/api/payments/topup/route.ts
git commit -m "feat(web): zamknutý účet nezaloží modelku ani nekúpi coiny"
```

---

## Task 7: Telegram webhook — tlačidlá Approve / Reject

**Files:**
- Create: `web/app/api/telegram/admin/route.ts`

- [ ] **Step 1: Napíš route**

```ts
import { NextResponse, type NextRequest } from "next/server";

import { telegramAdminChatId, telegramAdminWebhookSecret } from "@/lib/env";
import { createServiceClient } from "@/lib/supabase/server";
import { answerCallback, editMessageText } from "@/lib/telegram-admin";

/**
 * Webhook Marekovho súkromného admin bota — obsluhuje tlačidlá pod správou
 * o novej žiadosti.
 *
 * TRI NEZÁVISLÉ KONTROLY, každá by stačila sama:
 *   1. secret token v hlavičke (nastavený pri `setWebhook`)
 *   2. `chat.id` sedí s `TELEGRAM_ADMIN_CHAT_ID` — cudzí, kto bota nájde
 *      a napíše mu, neschváli nič
 *   3. `decide_access_request` je service_role-only; `authenticated` ju nemá
 *
 * Vraciame 200 aj pri odmietnutí: Telegram na non-200 doručovanie opakuje
 * a nezmyselný request by sa nám vracal donekonečna.
 */
export async function POST(request: NextRequest) {
  const secret = telegramAdminWebhookSecret();
  const adminChatId = telegramAdminChatId();

  if (!secret || !adminChatId) return NextResponse.json({ ok: true });
  if (request.headers.get("x-telegram-bot-api-secret-token") !== secret) {
    return NextResponse.json({ ok: true });
  }

  let update: {
    callback_query?: {
      id: string;
      data?: string;
      message?: { message_id: number; chat?: { id: number } };
    };
  };
  try {
    update = await request.json();
  } catch {
    return NextResponse.json({ ok: true });
  }

  const query = update.callback_query;
  if (!query?.data || !query.message) return NextResponse.json({ ok: true });
  if (String(query.message.chat?.id ?? "") !== adminChatId) {
    return NextResponse.json({ ok: true });
  }

  const match = /^acc:(ok|no):([0-9a-f-]{36})$/.exec(query.data);
  if (!match) return NextResponse.json({ ok: true });

  const approve = match[1] === "ok";
  const requestId = match[2];

  const supabase = createServiceClient();

  // Herca do auditu berieme z DB, nie z requestu — kto klikol, vieme z chat id,
  // ale zapísať treba účet, a ten je práve jeden.
  const { data: admin } = await supabase
    .from("accounts")
    .select("id")
    .eq("role", "superadmin")
    .order("created_at", { ascending: true })
    .limit(1)
    .maybeSingle();

  if (!admin) {
    await answerCallback(query.id, "No superadmin account found.");
    return NextResponse.json({ ok: true });
  }

  const { data: status, error } = await supabase.rpc("decide_access_request", {
    p_id: requestId,
    p_approve: approve,
    p_note: approve ? "" : "Rejected from Telegram",
    p_actor: admin.id,
  });

  if (error) {
    await answerCallback(query.id, "Failed — try the web panel.");
    return NextResponse.json({ ok: true });
  }

  const decided = String(status);
  await answerCallback(query.id, decided === "approved" ? "Approved" : "Rejected");
  await editMessageText({
    chatId: query.message.chat!.id,
    messageId: query.message.message_id,
    text:
      decided === "approved"
        ? "<b>Access request — approved ✅</b>"
        : "<b>Access request — rejected ✖️</b>",
  });

  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 2: Over meno service klienta**

Run: `cd web && grep -n "createServiceClient" lib/supabase/server.ts`
Expected: nájde export. Ak sa volá inak, oprav import v route.

- [ ] **Step 3: Build**

Run: `cd web && npm run typecheck && npm run build`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/app/api/telegram/admin/route.ts
git commit -m "feat(web): Telegram webhook na schválenie žiadosti"
```

---

## Task 8: Admin panel — záložka Requests

**Files:**
- Create: `web/lib/access-admin.ts`
- Create: `web/app/app/admin/requests/page.tsx`
- Create: `web/app/app/admin/requests/actions.ts`
- Create: `web/components/app/admin/requests-table.tsx`
- Modify: `web/components/app/admin/admin-tabs.tsx:9-14`

- [ ] **Step 1: `web/lib/access-admin.ts`**

```ts
import { adminErrorText } from "@/lib/admin-ui";
import { createClient } from "@/lib/supabase/server";

export type AdminAccessRequest = {
  id: string;
  accountId: string;
  email: string;
  plan: string;
  status: "pending" | "approved" | "rejected";
  message: string;
  createdAt: string;
  decidedAt: string | null;
  decidedNote: string;
  decidedByEmail: string | null;
};

type Raw = {
  id: string;
  account_id: string;
  email: string | null;
  plan: string;
  status: string;
  message: string | null;
  created_at: string;
  decided_at: string | null;
  decided_note: string | null;
  decided_by_email: string | null;
};

/** RPC je security definer + `where is_admin()`, takže cudzí nedostane nič. */
export async function listAccessRequests(): Promise<AdminAccessRequest[]> {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_list_access_requests");
  if (error) throw new Error(adminErrorText(error.message));

  return ((data ?? []) as Raw[]).map((row) => ({
    id: row.id,
    accountId: row.account_id,
    email: row.email ?? "",
    plan: row.plan,
    status: row.status as AdminAccessRequest["status"],
    message: row.message ?? "",
    createdAt: row.created_at,
    decidedAt: row.decided_at,
    decidedNote: row.decided_note ?? "",
    decidedByEmail: row.decided_by_email,
  }));
}
```

- [ ] **Step 2: `web/app/app/admin/requests/actions.ts`**

```ts
"use server";

import { revalidatePath } from "next/cache";

import { requireAdmin } from "@/lib/admin";
import { adminErrorText } from "@/lib/admin-ui";
import { createClient } from "@/lib/supabase/server";

export type DecideResult = { error?: string; status?: string };

/** Guard je tu aj v layoute aj v RPC — layout sa pri client navigácii nemusí
 *  prerátať, takže sa naň nespoliehame ako na jedinú obranu (vzor z 009). */
export async function decideRequestAction(
  requestId: string,
  approve: boolean,
  note: string,
): Promise<DecideResult> {
  await requireAdmin();

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_decide_access_request", {
    p_id: requestId,
    p_approve: approve,
    p_note: note.slice(0, 500),
  });

  if (error) return { error: adminErrorText(error.message) };

  revalidatePath("/app/admin/requests");
  revalidatePath("/app/admin/users");
  return { status: String(data) };
}
```

- [ ] **Step 3: `web/components/app/admin/requests-table.tsx`**

```tsx
"use client";

import { useState, useTransition } from "react";

import { decideRequestAction } from "@/app/app/admin/requests/actions";
import { useToast } from "@/components/app/admin/toast";
import type { AdminAccessRequest } from "@/lib/access-admin";

const STATUS_STYLE: Record<AdminAccessRequest["status"], string> = {
  pending: "border-[rgba(250,204,21,0.26)] text-[#fde047]",
  approved: "border-[rgba(74,222,128,0.28)] text-[#86efac]",
  rejected: "border-[#3f3f46] text-[#a1a1aa]",
};

export function RequestsTable({ rows }: { rows: AdminAccessRequest[] }) {
  const toast = useToast();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  function decide(row: AdminAccessRequest, approve: boolean) {
    setPendingId(row.id);
    startTransition(async () => {
      const result = await decideRequestAction(row.id, approve, "");
      setPendingId(null);
      if (result.error) toast.error(result.error);
      else if (result.status === "approved") toast.success(`${row.email} approved`);
      else toast.success(`${row.email} rejected`);
    });
  }

  if (rows.length === 0) {
    return (
      <p className="py-10 text-center text-[13.5px] text-[var(--app-text-3)]">
        No access requests yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-[var(--app-border)] text-left text-[var(--app-text-4)]">
            <th className="py-2 pr-4 font-normal">Account</th>
            <th className="py-2 pr-4 font-normal">Message</th>
            <th className="py-2 pr-4 font-normal">Status</th>
            <th className="py-2 pr-4 font-normal">Requested</th>
            <th className="py-2 font-normal" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const busy = pendingId === row.id;
            return (
              <tr key={row.id} className="border-b border-[var(--app-border)]/60 align-top">
                <td className="py-3 pr-4">
                  <div className="text-[var(--app-text)]">{row.email}</div>
                  <div className="text-[12px] text-[var(--app-text-4)]">{row.plan}</div>
                </td>
                <td className="max-w-sm py-3 pr-4 text-[var(--app-text-2)]">
                  {row.message || "—"}
                </td>
                <td className="py-3 pr-4">
                  <span
                    className={`inline-flex rounded border px-2 py-0.5 text-[11.5px] ${STATUS_STYLE[row.status]}`}
                  >
                    {row.status}
                  </span>
                </td>
                <td className="py-3 pr-4 text-[var(--app-text-3)]">
                  {new Date(row.createdAt).toLocaleDateString()}
                </td>
                <td className="py-3">
                  {row.status === "pending" && (
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => decide(row, true)}
                        className="app-btn app-btn-primary px-3! py-1.5! text-[12.5px]!"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => decide(row, false)}
                        className="app-btn app-btn-ghost px-3! py-1.5! text-[12.5px]!"
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: `web/app/app/admin/requests/page.tsx`**

```tsx
import { RequestsTable } from "@/components/app/admin/requests-table";
import { PageHeader } from "@/components/app/ui";
import { listAccessRequests } from "@/lib/access-admin";
import { requireAdmin } from "@/lib/admin";

export const metadata = { title: "Requests" };

export default async function AdminRequestsPage() {
  await requireAdmin();
  const rows = await listAccessRequests();
  const pending = rows.filter((row) => row.status === "pending").length;

  return (
    <>
      <PageHeader
        title="Access requests"
        description={
          pending === 0 ? "Nothing waiting." : `${pending} waiting for a decision.`
        }
      />
      <RequestsTable rows={rows} />
    </>
  );
}
```

`PageHeader` berie `{ title, description?, actions?, eyebrow? }`
(`web/components/app/ui.tsx:15`) — pozor, prop sa volá `description`, nie
`subtitle`.

- [ ] **Step 5: Pridaj záložku do `web/components/app/admin/admin-tabs.tsx`**

Nahraď `TABS` (riadky 9–14):

```tsx
const TABS = [
  { href: "/app/admin", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/app/admin/requests", label: "Requests", icon: UserPlus, exact: false },
  { href: "/app/admin/users", label: "Users", icon: Users, exact: false },
  { href: "/app/admin/models", label: "Models", icon: Bot, exact: false },
  { href: "/app/admin/usage", label: "Usage", icon: BarChart3, exact: false },
];
```

A rozšír import ikon:

```tsx
import { BarChart3, Bot, LayoutDashboard, UserPlus, Users } from "lucide-react";
```

- [ ] **Step 6: Build**

Run: `cd web && npm run typecheck && npm run build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web/lib/access-admin.ts web/app/app/admin/requests web/components/app/admin/requests-table.tsx web/components/app/admin/admin-tabs.tsx
git commit -m "feat(web): admin záložka so žiadosťami o prístup"
```

---

## Task 9: Nasadenie a ručná skúška

**Files:** žiadne (konfigurácia a overenie)

- [ ] **Step 1: Vygeneruj webhook secret**

Run: `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`
Expected: 64 hex znakov — ulož si ich

- [ ] **Step 2: Nastav env premenné vo Vercel (Production aj Preview)**

```
TELEGRAM_ADMIN_BOT_TOKEN=8668365722:AAFFumZ3lh0p0xuPs3_5I7QNYVh9p8jPErE
TELEGRAM_ADMIN_CHAT_ID=566608217
TELEGRAM_ADMIN_WEBHOOK_SECRET=<zo Step 1>
```

Tie isté tri riadky pridaj aj do `web/.env.local` pre lokálny vývoj.

- [ ] **Step 3: Deploy a registruj webhook**

Po nasadení (nech `<DOMAIN>` je produkčná doména):

```bash
node -e '
const t=process.env.TELEGRAM_ADMIN_BOT_TOKEN, s=process.env.TELEGRAM_ADMIN_WEBHOOK_SECRET;
fetch(`https://api.telegram.org/bot${t}/setWebhook`,{method:"POST",
 headers:{"Content-Type":"application/json"},
 body:JSON.stringify({url:"https://<DOMAIN>/api/telegram/admin",secret_token:s,allowed_updates:["callback_query"]})})
 .then(r=>r.json()).then(console.log)'
```

Expected: `{ ok: true, result: true, description: 'Webhook was set' }`

- [ ] **Step 4: Ručná skúška celej cesty**

1. Registruj nový testovací účet → musí pristáť na `/locked`
2. Skús ručne otvoriť `/app`, `/app/billing`, `/app/admin` → všetko redirect na `/locked`
3. Pošli žiadosť → do Telegramu príde správa s tlačidlami
4. Klikni **Approve** → správa sa prepíše na „approved ✅"
5. V testovacom účte refresh → workspace sa otvorí, dá sa založiť modelka
6. V admin paneli `/app/admin/users` → účet má plán **Standard+**
7. Skontroluj, že **Marekov aj kamarátov účet fungujú presne ako pred zmenou**

- [ ] **Step 5: Skús obísť zámok (musí zlyhať)**

Na zamknutom testovacom účte v konzole prehliadača:

```js
await window.__supabase?.from("models").insert({ account_id: "<id>", name: "hack" })
```

alebo priamo cez PostgREST s jeho access tokenom.
Expected: `new row violates row-level security policy for table "models"`

- [ ] **Step 6: Commit stavu dokumentácie**

```bash
git add -A && git commit -m "chore: nasadenie access gatingu" || true
```

---

## Čo tento plán ZÁMERNE nerieši

- **Notifikácie vo webe** (zvonček, `notifications`, Realtime) — vrstva 2.
  Preto je `decide_access_request` jediné miesto, kde sa schvaľuje: notifikáciu
  doň neskôr stačí dopísať a chytí obe cesty naraz.
- **Chat** (Community / Community+ / DM na admina) — vrstva 3. `/locked` je
  preto samostatná stránka s vlastným layoutom, nie slepá hláška — chat sa naň
  bude dať pripojiť.
- **E-mail žiadateľovi po schválení** — dnes v projekte mailová služba nie je.
  Text na `/locked` sľubuje e-mail; ak sa vrstva 2 spraví skôr, sľub sa zmení na
  in-app notifikáciu. Zosúladiť pri vrstve 2.
- **Automatické pauzovanie replík pri odobratí Standard+** — vedomé rozhodnutie
  zo spec-u: dáta ostávajú, worker beží.

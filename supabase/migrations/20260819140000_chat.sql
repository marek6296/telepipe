-- Chat: Community (všetci), Community+ (len odomknutí), DM na admina.
--
-- Prístup rozhoduje JEDNA funkcia `chat_room_visible()`, ktorá stojí na
-- `account_unlocked()` z vrstvy 1 — nechceme druhé miesto, kde sa rozhoduje
-- o odomknutí. Keby sa tie dve rozišli, Community+ by sa otvoril niekomu, koho
-- Marek nepustil dnu.

create table if not exists chat_rooms (
  id               uuid primary key default gen_random_uuid(),
  kind             text not null check (kind in ('community', 'community_plus', 'admin_dm')),
  owner_account_id uuid references accounts(id) on delete cascade,
  created_at       timestamptz not null default now(),
  -- admin_dm MUSÍ mať majiteľa, verejné kanály ho mať NESMÚ.
  constraint chat_rooms_owner_shape check (
    (kind = 'admin_dm' and owner_account_id is not null)
    or (kind <> 'admin_dm' and owner_account_id is null)
  )
);

-- Community a Community+ sú po jednej; DM je jedna na účet.
create unique index if not exists chat_rooms_one_public
  on chat_rooms (kind) where kind in ('community', 'community_plus');
create unique index if not exists chat_rooms_one_dm_per_account
  on chat_rooms (owner_account_id) where kind = 'admin_dm';

insert into chat_rooms (kind)
select 'community' where not exists (select 1 from chat_rooms where kind = 'community');
insert into chat_rooms (kind)
select 'community_plus' where not exists (select 1 from chat_rooms where kind = 'community_plus');

create table if not exists chat_messages (
  id         uuid primary key default gen_random_uuid(),
  room_id    uuid not null references chat_rooms(id) on delete cascade,
  sender_id  uuid not null references accounts(id) on delete cascade,
  body       text not null default '',
  image_path text not null default '',
  deleted_at timestamptz,
  deleted_by uuid references accounts(id) on delete set null,
  created_at timestamptz not null default now(),
  constraint chat_messages_not_empty check (body <> '' or image_path <> '')
);

create index if not exists chat_messages_room_recent
  on chat_messages (room_id, created_at desc);

create table if not exists chat_reads (
  room_id      uuid not null references chat_rooms(id) on delete cascade,
  account_id   uuid not null references accounts(id) on delete cascade,
  last_read_at timestamptz not null default now(),
  primary key (room_id, account_id)
);

create table if not exists chat_mutes (
  account_id uuid primary key references accounts(id) on delete cascade,
  muted_by   uuid references accounts(id) on delete set null,
  reason     text not null default '',
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Pravidlá prístupu
-- ---------------------------------------------------------------------------

-- `is_admin()` z 009 pozerá na auth.uid(); tu treba rozhodnúť o ĽUBOVOĽNOM účte
-- (napr. či je adminom odosielateľ vnútri policy).
create or replace function account_is_admin(p_account uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $fn$
  select exists (
    select 1 from accounts where id = p_account and role in ('admin', 'superadmin')
  );
$fn$;
revoke execute on function account_is_admin(uuid) from public, anon;
grant execute on function account_is_admin(uuid) to authenticated, service_role;

create or replace function chat_room_visible(p_room uuid, p_account uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $fn$
  select case r.kind
    when 'community'      then true
    when 'community_plus' then account_unlocked(p_account)
    when 'admin_dm'       then r.owner_account_id = p_account or account_is_admin(p_account)
    else false
  end
  from chat_rooms r where r.id = p_room;
$fn$;
revoke execute on function chat_room_visible(uuid, uuid) from public, anon;
grant execute on function chat_room_visible(uuid, uuid) to authenticated, service_role;

-- Umlčaný ďalej ČÍTA, len nepíše — rieši spamera bez toho, aby prišiel o produkt.
create or replace function chat_can_post(p_room uuid, p_account uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $fn$
  select coalesce(chat_room_visible(p_room, p_account), false)
     and not exists (select 1 from chat_mutes where account_id = p_account);
$fn$;
revoke execute on function chat_can_post(uuid, uuid) from public, anon;
grant execute on function chat_can_post(uuid, uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table chat_rooms enable row level security;
revoke all on chat_rooms from anon, authenticated;
grant select (id, kind, owner_account_id, created_at) on chat_rooms to authenticated;
drop policy if exists chat_rooms_visible on chat_rooms;
create policy chat_rooms_visible on chat_rooms
  for select to authenticated using (chat_room_visible(id, (select auth.uid())));

alter table chat_messages enable row level security;
revoke all on chat_messages from anon, authenticated;
grant select (id, room_id, sender_id, body, image_path, deleted_at, created_at)
  on chat_messages to authenticated;
grant insert (room_id, sender_id, body, image_path) on chat_messages to authenticated;

drop policy if exists chat_messages_visible on chat_messages;
create policy chat_messages_visible on chat_messages
  for select to authenticated
  using (chat_room_visible(room_id, (select auth.uid())));

-- Fotky IBA v admin_dm. UI nie je hranica, tak sa to vynucuje tu.
drop policy if exists chat_messages_send on chat_messages;
create policy chat_messages_send on chat_messages
  for insert to authenticated
  with check (
    sender_id = (select auth.uid())
    and chat_can_post(room_id, (select auth.uid()))
    and (
      image_path = ''
      or exists (select 1 from chat_rooms r where r.id = room_id and r.kind = 'admin_dm')
    )
  );

-- Žiadny UPDATE ani DELETE policy: mazanie je výhradne adminove a ide cez RPC
-- ako soft delete. Bežný človek si vlastnú správu zmazať nevie (Marekova voľba).

alter table chat_reads enable row level security;
revoke all on chat_reads from anon, authenticated;
grant select (room_id, account_id, last_read_at) on chat_reads to authenticated;
grant insert (room_id, account_id, last_read_at) on chat_reads to authenticated;
grant update (last_read_at) on chat_reads to authenticated;
drop policy if exists chat_reads_own on chat_reads;
create policy chat_reads_own on chat_reads
  for all to authenticated
  using (account_id = (select auth.uid()))
  with check (account_id = (select auth.uid()) and chat_room_visible(room_id, (select auth.uid())));

alter table chat_mutes enable row level security;
revoke all on chat_mutes from anon, authenticated;
grant select (account_id, reason, created_at) on chat_mutes to authenticated;
drop policy if exists chat_mutes_own on chat_mutes;
create policy chat_mutes_own on chat_mutes
  for select to authenticated using (account_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- RPC
-- ---------------------------------------------------------------------------

-- Moja DM na admina — vráti existujúcu alebo založí. Idempotentné.
create or replace function my_dm_room()
returns uuid language plpgsql security definer
set search_path = public, pg_temp as $fn$
declare v_account uuid := auth.uid(); v_id uuid;
begin
  if v_account is null then raise exception 'not authenticated' using errcode = '42501'; end if;

  select id into v_id from chat_rooms
   where kind = 'admin_dm' and owner_account_id = v_account;
  if v_id is not null then return v_id; end if;

  insert into chat_rooms (kind, owner_account_id) values ('admin_dm', v_account)
  on conflict do nothing
  returning id into v_id;

  -- Súbeh dvoch tabov: unique index vyhral ten druhý, dotiahni jeho riadok.
  if v_id is null then
    select id into v_id from chat_rooms
     where kind = 'admin_dm' and owner_account_id = v_account;
  end if;
  return v_id;
end;
$fn$;
revoke execute on function my_dm_room() from public, anon;
grant execute on function my_dm_room() to authenticated;

create or replace function admin_delete_chat_message(p_id uuid)
returns boolean language plpgsql security definer
set search_path = public, pg_temp as $fn$
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  update chat_messages
     set deleted_at = now(), deleted_by = auth.uid()
   where id = p_id and deleted_at is null;
  return found;
end;
$fn$;
revoke execute on function admin_delete_chat_message(uuid) from public, anon;
grant execute on function admin_delete_chat_message(uuid) to authenticated;

create or replace function admin_set_chat_mute(p_account uuid, p_muted boolean, p_reason text default '')
returns boolean language plpgsql security definer
set search_path = public, pg_temp as $fn$
begin
  if not is_admin() then raise exception 'forbidden' using errcode = '42501'; end if;
  -- Admina umlčať nejde: inak by si dvaja admini vedeli navzájom zavrieť ústa.
  if account_is_admin(p_account) then
    raise exception 'cannot mute an admin' using errcode = '42501';
  end if;

  if p_muted then
    insert into chat_mutes (account_id, muted_by, reason)
    values (p_account, auth.uid(), left(coalesce(p_reason, ''), 200))
    on conflict (account_id) do update set muted_by = excluded.muted_by, reason = excluded.reason;
  else
    delete from chat_mutes where account_id = p_account;
  end if;
  return p_muted;
end;
$fn$;
revoke execute on function admin_set_chat_mute(uuid, boolean, text) from public, anon;
grant execute on function admin_set_chat_mute(uuid, boolean, text) to authenticated;

-- Zoznam DM konverzácií pre admina — kto napísal, kedy, koľko neprečítaných.
create or replace function admin_list_dm_rooms()
returns table (
  room_id uuid, account_id uuid, email text, last_message_at timestamptz,
  last_body text, unread bigint
)
language sql stable security definer
set search_path = public, pg_temp as $fn$
  select r.id, r.owner_account_id, a.email,
         m.created_at, m.body,
         (select count(*) from chat_messages x
           where x.room_id = r.id and x.deleted_at is null
             and x.sender_id = r.owner_account_id
             and x.created_at > coalesce(
                   (select cr.last_read_at from chat_reads cr
                     where cr.room_id = r.id and cr.account_id = auth.uid()),
                   'epoch'::timestamptz))
  from chat_rooms r
  join accounts a on a.id = r.owner_account_id
  left join lateral (
    select body, created_at from chat_messages
     where room_id = r.id and deleted_at is null
     order by created_at desc limit 1
  ) m on true
  where is_admin() and r.kind = 'admin_dm'
  order by m.created_at desc nulls last
  limit 200;
$fn$;
revoke execute on function admin_list_dm_rooms() from public, anon;
grant execute on function admin_list_dm_rooms() to authenticated;

-- Realtime
do $pub$
begin
  if not exists (
    select 1 from pg_publication_tables
     where pubname = 'supabase_realtime' and schemaname = 'public'
       and tablename = 'chat_messages'
  ) then
    alter publication supabase_realtime add table chat_messages;
  end if;
end $pub$;

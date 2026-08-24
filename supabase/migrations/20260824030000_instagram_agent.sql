-- Dátová vrstva Instagram agenta: ľudia a správy.
--
-- PREČO VLASTNÉ TABUĽKY A NIE `dm_users`. Je to tá istá OSOBA, ale iná
-- konverzácia s iným človekom na inej platforme — presne ako Fanvue má
-- `fv_users`/`fv_messages`. Miešať ich do telegramových by znamenalo, že
-- štatistiky, denný súhrn aj okno konverzácie zrazu počítajú dokopy dve
-- rôzne veci.
--
-- ČÍTA SA POLLOVANÍM, NIE WEBHOOKMI. Webhooky Instagramu vyžadujú Advanced
-- Access AJ overenie firmy (dokumentácia, Setup Webhooks Subscriptions), takže
-- na vlastnom účte sa nedajú zapnúť. Conversations API stačí Standard Access —
-- agent teda ťahá konverzácie sám a `last_mid` je vodoznak, po ktorý ich už
-- spracoval.

create table if not exists ig_users (
  model_id uuid not null references models(id) on delete cascade,
  -- Instagram-scoped ID: to isté konto má pri každej appke iné id, takže je to
  -- identita v rámci NAŠEJ appky, nie globálny účet.
  igsid text not null,

  username text not null default '',
  name text not null default '',

  msg_count int not null default 0,
  funnel_stage text not null default 'cold',
  -- Kam mu už povedala, že ju nájde. Na Instagrame to nie je odkaz na platenú
  -- platformu, ale telegramové meno alebo rozcestník v biu.
  pointed_at timestamptz,
  pointed_count int not null default 0,

  ai_enabled boolean not null default true,
  human_takeover boolean not null default false,

  summary text not null default '',
  summary_at_msg int not null default 0,

  last_incoming_at timestamptz,
  last_reply_at timestamptz,
  created_at timestamptz not null default now(),

  primary key (model_id, igsid)
);

create table if not exists ig_messages (
  model_id uuid not null references models(id) on delete cascade,
  id bigserial primary key,
  igsid text not null,
  -- `mid` z Instagramu. Konverzácie sa ťahajú opakovane, takže bez neho by tá
  -- istá správa pribudla do histórie pri každom kole.
  mid text not null default '',
  role text not null check (role in ('user', 'assistant')),
  content text not null default '',
  created_at timestamptz not null default now()
);

create unique index if not exists ig_messages_mid_idx
  on ig_messages (model_id, mid) where mid <> '';
create index if not exists ig_messages_chat_idx
  on ig_messages (model_id, igsid, created_at desc);

-- Vodoznak pollovania a čas posledného kola. Bez nich by agent po reštarte
-- prešiel celú históriu odznova a odpovedal na týždeň staré správy.
alter table instagram
  add column if not exists last_poll_at timestamptz,
  add column if not exists poll_error text not null default '';

comment on table ig_users is
  'Ľudia, ktorí písali modelke na Instagrame. Instagram-scoped ID je identita '
  'v rámci našej appky, nie globálny účet.';
comment on column ig_users.pointed_at is
  'Kedy mu naposledy povedala, kde ju nájde (Telegram alebo odkaz v biu). '
  'Odkaz na platenú platformu sem nepatrí — na Instagrame je to dôvod na ban.';

-- Klient smie svoje konverzácie ČÍTAŤ (dashboard), zapisovať ich smie worker.
alter table ig_users enable row level security;
alter table ig_messages enable row level security;

revoke all on ig_users from anon, authenticated;
revoke all on ig_messages from anon, authenticated;

drop policy if exists ig_users_owner_select on ig_users;
create policy ig_users_owner_select on ig_users
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

drop policy if exists ig_messages_owner_select on ig_messages;
create policy ig_messages_owner_select on ig_messages
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

grant select on ig_users to authenticated;
grant select on ig_messages to authenticated;

do $$
begin
  if has_table_privilege('authenticated', 'ig_messages', 'INSERT') then
    raise exception 'ig_messages: klient si vie dopísať históriu';
  end if;
  if has_table_privilege('authenticated', 'ig_users', 'UPDATE') then
    raise exception 'ig_users: klient si vie prepísať konverzáciu';
  end if;
  if not has_table_privilege('authenticated', 'ig_users', 'SELECT') then
    raise exception 'ig_users: klient nevidí vlastné konverzácie';
  end if;
  raise notice 'ig_users a ig_messages OK';
end $$;

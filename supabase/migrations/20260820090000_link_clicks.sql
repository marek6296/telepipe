-- Meranie klikov na odkaz: krátky odkaz cez našu doménu.
--
-- PREČO. Jedenásť ľudí dostalo odkaz, nula zaplatila — a nedalo sa zistiť,
-- ktorá polovica je pokazená. „Nikto neklikol" a „klikli a nekúpili" sú dve
-- opačné diagnózy a robí sa proti nim opak: prvá je vec konverzácie, druhá vec
-- samotnej Fanvue stránky. Bez tohto stĺpca sa medzi nimi rozhodovalo hádaním.
--
-- CIEĽ SA NEUKLADÁ. Odkaz sa skladá až pri kliknutí z aktuálnej `persona.cta_link`
-- — vďaka tomu odkaz poslaný minulý týždeň funguje aj po tom, ako si klient
-- stránku premenuje. Token nesie len to, KOMU bol odkaz poslaný.

create table if not exists short_links (
  token text primary key,
  model_id uuid not null references models(id) on delete cascade,
  tg_id bigint not null,
  created_at timestamptz not null default now(),
  clicks int not null default 0,
  first_click_at timestamptz,
  last_click_at timestamptz,
  unique (model_id, tg_id)
);

comment on table short_links is
  'Krátky odkaz na jednu konverzáciu. Token je náhodný a nesie len dvojicu '
  'model+tg_id; cieľ sa skladá pri kliknutí z aktuálnej persony.';

create index if not exists short_links_model_idx on short_links (model_id);

-- Kedy naposledy otvoril stránku. Sedí na `dm_users`, lebo je to vlastnosť
-- konverzácie — číta to worker (upozornenie do bota) aj karta konverzácie.
alter table dm_users
  add column if not exists link_clicked_at timestamptz;

comment on column dm_users.link_clicked_at is
  'Kedy naposledy otvoril odkaz. Zapisuje presmerovanie na webe (service role), '
  'worker to prečíta a ohlási majiteľovi.';

-- Poistka proti dvom upozorneniam na ten istý klik.
alter table dm_users
  add column if not exists click_notified_at timestamptz;

-- Supabase dáva `authenticated` na novú tabuľku plné práva cez default
-- privileges. Klient smie svoje kliky VIDIEŤ (dashboard), ale nie prepisovať —
-- inak si vie dokresliť štatistiku, ktorá má byť dôkazom.
revoke all on short_links from authenticated;
grant select on short_links to authenticated;

do $$
begin
  if has_table_privilege('authenticated', 'short_links', 'UPDATE')
     or has_table_privilege('authenticated', 'short_links', 'INSERT')
     or has_table_privilege('authenticated', 'short_links', 'DELETE') then
    raise exception 'short_links: klient smie prepisovať kliky';
  end if;
  if not has_table_privilege('authenticated', 'short_links', 'SELECT') then
    raise exception 'short_links: klient nevidí vlastné kliky';
  end if;
  if has_column_privilege('authenticated', 'dm_users', 'link_clicked_at', 'UPDATE') then
    raise exception 'link_clicked_at: klient to môže prepísať';
  end if;
  raise notice 'short_links OK';
end $$;

-- RLS: klient vidí len kliky svojich modeliek.
alter table short_links enable row level security;

drop policy if exists short_links_own on short_links;
-- Rovnaký tvar ako `dm_users_owner_select`: `models.account_id` JE id
-- prihláseného používateľa, žiadny join na `accounts` netreba.
create policy short_links_own on short_links
  for select to authenticated
  using (
    model_id in (select id from models where account_id = (select auth.uid()))
  );

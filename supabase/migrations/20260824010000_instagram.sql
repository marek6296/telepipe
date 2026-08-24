-- Tretí agent: Instagram.
--
-- OFICIÁLNA CESTA, NIE PRIHLÁSENIE MENOM A HESLOM. Telegram beží cez Telethon
-- session, lebo inak sa to nedá; Instagram má oficiálne API a to sa použije.
-- Overené v dokumentácii (Business Login for Instagram, aktualizovaná 13. 3.
-- 2026): „This API setup does not require a Facebook Page to be linked to the
-- Instagram professional account." Stačí teda profesionálny (business alebo
-- creator) účet — Facebook stránka nie.
--
-- ŽIVOTNOSŤ TOKENU JE 60 DNÍ a to je dôvod, prečo tu je `token_expires_at`.
-- Dlhodobý token sa dá obnoviť o ďalších 60 dní, ale LEN kým je platný; token,
-- ktorý sa 60 dní neobnovil, je nenávratne mŕtvy. Bez tohto stĺpca by sa na to
-- prišlo až tým, že modelka dva mesiace po pripojení prestane odpisovať.
--
-- ODKAZ NA FANVUE SEM NEPATRÍ. Na Instagrame je odkaz na stránku pre dospelých
-- dôvod na ban účtu, takže agent ťahá ľudí na Telegram alebo na rozcestník
-- v biu. Preto `funnel_target` a dve polia na cieľ — a preto tu nie je nič,
-- do čoho by sa dala vložiť adresa Fanvue.

create table if not exists instagram (
  model_id uuid primary key references models(id) on delete cascade,

  connected boolean not null default false,

  -- Vypínač ODPISOVANIA, nie pripojenia — rovnaké rozdelenie ako pri Fanvue.
  -- Default `false`: táto migrácia prináša pripojenie a nastavenia, agent vo
  -- workeri príde až potom. Kým je `false`, nemá to čo odpisovať.
  enabled boolean not null default false,

  -- Token je dlhodobý (60 dní). Refresh token neexistuje — obnovuje sa ten
  -- istý token cez `/refresh_access_token`, preto je tu len jeden stĺpec.
  access_token_enc text not null default '',
  token_expires_at timestamptz,
  scope text not null default '',

  -- Identita na Instagrame. `ig_user_id` je zároveň adresa, na ktorú chodia
  -- webhooky — všetky modelky zdieľajú jeden endpoint a rozlíši ich až id.
  ig_user_id text not null default '',
  username text not null default '',
  account_type text not null default '',

  -- Kam ťahá ľudí. `telegram` = pošle jej telegramové meno, `bio_link` = odkaz
  -- na rozcestník. Fanvue medzi možnosťami zámerne nie je.
  funnel_target text not null default 'telegram'
    check (funnel_target in ('telegram', 'bio_link')),
  telegram_handle text not null default '',
  bio_link text not null default '',

  -- Režim odpovedania, rovnaké hodnoty ako Telegram a Fanvue.
  reply_mode text not null default 'off'
    check (reply_mode in ('off', 'auto', 'semi')),

  -- Instagram je verejnejší a prísnejší než Telegram: default je najmiernejší
  -- stupeň a klient si ho zdvihnúť môže, ale `hot` tu nie je vôbec.
  heat text not null default 'mild' check (heat in ('mild', 'medium')),

  -- Odpovedať aj na komentáre pod príspevkami, nielen na DM.
  reply_comments boolean not null default false,

  last_error text not null default '',
  connected_at timestamptz,
  updated_at timestamptz not null default now()
);

comment on table instagram is
  'Pripojenie a nastavenia Instagram agenta. Oficiálne API (Business Login for '
  'Instagram) — profesionálny účet stačí, Facebook stránka netreba.';
comment on column instagram.token_expires_at is
  'Dlhodobý token platí 60 dní a obnoviť sa dá len kým je platný. Po expirácii '
  'sa musí klient pripojiť nanovo.';
comment on column instagram.funnel_target is
  'Kam ťahá ľudí. Fanvue tu nie je zámerne — odkaz na stránku pre dospelých je '
  'na Instagrame dôvod na ban.';

-- Jeden Instagram účet nesmie byť pripojený k dvom modelkám — inak by webhook
-- nemal ako rozhodnúť, komu správa patrí.
create unique index if not exists instagram_user_idx on instagram (ig_user_id)
  where ig_user_id <> '';

-- Riadok zakladá ten istý trigger ako ostatné tabuľky modelky.
insert into instagram (model_id)
select id from models where not exists (
  select 1 from instagram i where i.model_id = models.id
);

alter table instagram enable row level security;

-- Supabase dáva `authenticated` plné práva cez default privileges, takže
-- stĺpcové granty by sa len pridali navrch a token by ostal čitateľný. Preto
-- sa najprv odoberá všetko.
revoke all on instagram from anon, authenticated;

drop policy if exists instagram_owner_select on instagram;
create policy instagram_owner_select on instagram
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

drop policy if exists instagram_owner_update on instagram;
create policy instagram_owner_update on instagram
  for update to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

-- Token NIE JE medzi čitateľnými stĺpcami a nikdy nesmie byť: prehliadač ho
-- nepotrebuje a únik tokenu je únik celého účtu.
grant select (model_id, connected, enabled, ig_user_id, username, account_type,
              funnel_target, telegram_handle, bio_link, reply_mode, heat,
              reply_comments, token_expires_at, last_error, connected_at,
              updated_at)
  on instagram to authenticated;

-- Meniť smie klient len to, čo je nastavenie. `connected`, `enabled` a token
-- sú vec servera.
grant update (funnel_target, telegram_handle, bio_link, reply_mode, heat,
              reply_comments)
  on instagram to authenticated;

do $$
declare
  v_model uuid;
  v_ok boolean := false;
begin
  if has_column_privilege('authenticated', 'instagram', 'access_token_enc', 'SELECT') then
    raise exception 'instagram: klient vidí token';
  end if;
  if has_column_privilege('authenticated', 'instagram', 'connected', 'UPDATE') then
    raise exception 'instagram: klient si vie nastaviť, že je pripojený';
  end if;
  if not has_column_privilege('authenticated', 'instagram', 'funnel_target', 'UPDATE') then
    raise exception 'instagram: klient si nevie nastaviť lievik';
  end if;

  select model_id into v_model from instagram limit 1;
  if v_model is not null then
    begin
      update instagram set funnel_target = 'fanvue' where model_id = v_model;
    exception when check_violation then v_ok := true;
    end;
    if not v_ok then
      raise exception 'instagram: fanvue prešlo ako cieľ lievika';
    end if;

    v_ok := false;
    begin
      update instagram set heat = 'hot' where model_id = v_model;
    exception when check_violation then v_ok := true;
    end;
    if not v_ok then
      raise exception 'instagram: hot prešlo ako pikantnosť';
    end if;
  end if;

  raise notice 'instagram OK';
end $$;

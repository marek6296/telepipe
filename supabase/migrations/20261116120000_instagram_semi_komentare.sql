-- Instagram: schvaľovacie karty (semi) a odpovede pod komentáre.
--
-- 1) `pending_replies.channel` doteraz poznal len telegram a fanvue, takže
--    semi režim Instagramu nemal kam uložiť kartu a majiteľovi chodila len
--    obyčajná správa bez tlačidiel. Odteraz idú Instagram návrhy tou istou
--    cestou ako Telegram a Fanvue.
--
-- 2) `ig_comments` = ktoré komentáre už agent vybavil. Instagram odpoveď pod
--    komentár nepovažuje za „prečítané" a komentáre sa ťahajú opakovane — bez
--    tejto tabuľky by pod ten istý komentár odpovedal v každom kole.

alter table pending_replies drop constraint if exists pending_replies_channel_check;
alter table pending_replies
  add constraint pending_replies_channel_check
  check (channel = any (array['telegram'::text, 'fanvue'::text, 'instagram'::text]));

create table if not exists ig_comments (
  model_id uuid not null references models(id) on delete cascade,
  comment_id text not null,
  media_id text not null default '',
  username text not null default '',
  text text not null default '',
  reply_text text not null default '',
  -- replied = odpoveď odišla · skipped = model povedal SKIP (spam, urážka)
  -- · failed = Instagram odpoveď odmietol (neskúša sa znova, aby sa nezacyklil)
  status text not null default 'replied'
    check (status in ('replied', 'skipped', 'failed')),
  created_at timestamptz not null default now(),
  primary key (model_id, comment_id)
);

create index if not exists ig_comments_model_idx
  on ig_comments (model_id, created_at desc);

comment on table ig_comments is
  'Komentáre pod príspevkami, ktoré Instagram agent už vybavil (odpovedal alebo '
  'preskočil). Zapisuje len worker.';

-- Klient smie svoje komentáre čítať (dashboard), zapisuje ich len worker.
alter table ig_comments enable row level security;
revoke all on ig_comments from anon, authenticated;

drop policy if exists ig_comments_owner_select on ig_comments;
create policy ig_comments_owner_select on ig_comments
  for select to authenticated
  using (model_id in (select id from models where account_id = (select auth.uid())));

grant select on ig_comments to authenticated;

-- `last_incoming_at` sa doteraz nezapisoval nikde; zoznam chatov v control
-- bote sa podľa neho radí.
create index if not exists ig_users_incoming_idx
  on ig_users (model_id, last_incoming_at desc nulls last);

do $$
begin
  if has_table_privilege('authenticated', 'ig_comments', 'INSERT') then
    raise exception 'ig_comments: klient si vie dopísať komentár';
  end if;
  if not has_table_privilege('authenticated', 'ig_comments', 'SELECT') then
    raise exception 'ig_comments: klient nevidí vlastné komentáre';
  end if;
  raise notice 'ig_comments OK';
end $$;

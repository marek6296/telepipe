-- Bucket na fotky v DM.
--
-- ZÁMERNE privátny — `photos` aj `voices` sú verejné, a súkromná fotka medzi
-- klientom a Marekom sa do verejného bucketu dať nesmie. Obrázok sa servíruje
-- výhradne cez signed URL z `/api/chat/image`.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('chat', 'chat', false, 10485760,
        array['image/jpeg', 'image/png', 'image/webp', 'image/gif'])
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- Cesta je vždy `dm/<owner_account_id>/<uuid>.<ext>`, takže druhý segment je
-- účet, ktorého DM to je. Prístup má majiteľ + admini (aby Marek vedel do DM
-- poslať screenshot naspäť).

drop policy if exists chat_upload on storage.objects;
create policy chat_upload on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'chat'
    and (storage.foldername(name))[1] = 'dm'
    and (
      (storage.foldername(name))[2] = (select auth.uid())::text
      or account_is_admin((select auth.uid()))
    )
  );

drop policy if exists chat_read on storage.objects;
create policy chat_read on storage.objects
  for select to authenticated
  using (
    bucket_id = 'chat'
    and (storage.foldername(name))[1] = 'dm'
    and (
      (storage.foldername(name))[2] = (select auth.uid())::text
      or account_is_admin((select auth.uid()))
    )
  );

-- Žiadne UPDATE/DELETE policy: raz poslanú fotku už nikto neprepíše.

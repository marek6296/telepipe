-- Storage policies pre bucket `photos` (fáza 2, W10 upload z webu).
--
-- Bucket je public → sťahovanie cez /object/public/... funguje bez policy.
-- Zápis smie robiť len prihlásený majiteľ a len do priečinka vlastnej modelky
-- (cesta `{model_id}/{uuid}.jpg`), inak by si klienti prepisovali fotky
-- navzájom. Voices bucket zostáva service-role only (fáza 3).

create policy photos_owner_select on storage.objects
  for select to authenticated
  using (
    bucket_id = 'photos'
    and (storage.foldername(name))[1] in (
      select id::text from models where account_id = (select auth.uid())
    )
  );

create policy photos_owner_insert on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'photos'
    and (storage.foldername(name))[1] in (
      select id::text from models where account_id = (select auth.uid())
    )
  );

create policy photos_owner_update on storage.objects
  for update to authenticated
  using (
    bucket_id = 'photos'
    and (storage.foldername(name))[1] in (
      select id::text from models where account_id = (select auth.uid())
    )
  )
  with check (
    bucket_id = 'photos'
    and (storage.foldername(name))[1] in (
      select id::text from models where account_id = (select auth.uid())
    )
  );

create policy photos_owner_delete on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'photos'
    and (storage.foldername(name))[1] in (
      select id::text from models where account_id = (select auth.uid())
    )
  );

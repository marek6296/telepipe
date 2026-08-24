-- Riadok Instagramu zakladá ten istý trigger ako personu a nastavenia bota.
--
-- Bez toho by nová modelka otvorila kartu bez riadku a nastavenia by nemalo čo
-- uložiť — `update ... where model_id = ...` by ticho zmenil nula riadkov a
-- klient by videl formulár, ktorý sa tvári, že ukladá.
--
-- Fanvue v tomto zozname zámerne NIE JE: jeho riadok vzniká až pri pripojení
-- (upsert v callbacku), lebo bez tokenu nemá čo obsahovať. Instagram má
-- nastavenia, ktoré dávajú zmysel aj pred pripojením (kam ťahá ľudí, ako ďaleko
-- smie zájsť), preto patrí sem.

create or replace function public.provision_model_rows()
 returns trigger
 language plpgsql
 security definer
 set search_path to 'public', 'pg_temp'
as $function$
begin
  insert into persona              (model_id) values (new.id) on conflict do nothing;
  insert into behavior             (model_id) values (new.id) on conflict do nothing;
  insert into settings             (model_id) values (new.id) on conflict do nothing;
  insert into model_schedule       (model_id) values (new.id) on conflict do nothing;
  insert into control_bot_settings (model_id) values (new.id) on conflict do nothing;
  insert into instagram            (model_id) values (new.id) on conflict do nothing;
  return new;
end;
$function$;

do $$
begin
  if not exists (
    select 1 from pg_proc
    where proname = 'provision_model_rows'
      and pg_get_functiondef(oid) like '%insert into instagram%'
  ) then
    raise exception 'provision_model_rows: instagram sa nezakladá';
  end if;
  raise notice 'provision_model_rows OK';
end $$;

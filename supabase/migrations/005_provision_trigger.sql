-- Každý model potrebuje svoje singleton riadky (persona, behavior, settings)
-- hneď od vzniku — worker aj web ich len PATCHujú a PATCH na neexistujúci
-- riadok ticho nič nespraví. Trigger je jediné miesto, ktoré ich zakladá,
-- takže na to nemôže zabudnúť ani web, ani ručný INSERT v SQL editore.
create or replace function provision_model_rows()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
  insert into persona  (model_id) values (new.id) on conflict do nothing;
  insert into behavior (model_id) values (new.id) on conflict do nothing;
  insert into settings (model_id) values (new.id) on conflict do nothing;
  return new;
end;
$$;

create trigger models_provision_rows
  after insert on models
  for each row execute function provision_model_rows();

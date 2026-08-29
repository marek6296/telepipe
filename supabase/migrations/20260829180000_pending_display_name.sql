-- Ako sa ten človek volá — aby to karta vedela aj po prekreslení.
--
-- STALO SA NAOSTRO. Karta ukazuje rozhovor riadok po riadku a pred každý sa
-- odteraz píše meno („Fashionable Snipe: …" / „Simona: …"), inak sa v ňom
-- nedá vyznať. Meno pritom poznal len ten kód, ktorý kartu poslal PRVÝKRÁT.
-- Pri „Regenerate" a pri návrate z foto-wizardu sa karta skladá z uloženého
-- riadku, a tam meno nebolo — dosadzoval sa `conv_key`, teda na Fanvue holé
-- uuid. Nadpis karty tak znel „Fanvue · 977dbb79-641e-…" a po tejto zmene by
-- to uuid stálo pred každou jeho vetou.
--
-- Prázdny reťazec = riadok spred tejto zmeny; karta vtedy spadne na `conv_key`
-- ako doteraz, nič sa nerozbije.
alter table pending_replies
  add column if not exists display_name text not null default '';

comment on column pending_replies.display_name is
  'Meno fanúšika v čase vzniku karty. Karta sa z riadku skladá znova pri '
  '„Regenerate" a po foto-wizarde — bez tohto by tam bol conv_key (uuid).';

do $$
begin
  -- Zapisuje worker cez service kľúč. Klient túto tabuľku iba číta a nový
  -- stĺpec v jeho stĺpcových grantoch nie je — nech tam ani nepribudne.
  if not has_column_privilege('service_role', 'pending_replies', 'display_name', 'INSERT') then
    raise exception 'display_name: worker to nevie zapísať';
  end if;
  if has_column_privilege('authenticated', 'pending_replies', 'display_name', 'UPDATE') then
    raise exception 'display_name: klient to môže prepísať';
  end if;
  raise notice 'pending_replies.display_name OK';
end $$;

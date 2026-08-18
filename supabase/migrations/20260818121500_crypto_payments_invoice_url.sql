-- Alternative Payment Link: Plisio pri zapnutom "Activate Alternative Payment
-- Link" vracia aj pri white-label shope `invoice_url` — hostovanú platobnú
-- stránku. Ukladáme ju a v checkoute ponúkame ako záložnú cestu (mobilné
-- peňaženky, ľudia čo chcú platiť z telefónu a pod.).
alter table crypto_payments add column invoice_url text not null default '';

grant select (invoice_url) on crypto_payments to authenticated;

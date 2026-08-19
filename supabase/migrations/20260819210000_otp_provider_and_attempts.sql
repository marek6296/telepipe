-- Dva zdroje OTP čísel a model „tri pokusy v cene".
--
-- PREČO PROVIDER V RIADKU: 5sim a VRNUM používajú INÉ identifikátory krajín
-- (5sim „colombia", VRNUM kód) aj iné id objednávok. Bez záznamu o tom, kto
-- objednávku vybavil, by sa po prepnutí providera staré objednávky nedali
-- dopýtať ani zrušiť — a to sú objednávky, za ktoré klient zaplatil.
--
-- PREČO POKUSY: predávame za 5× nákupku a v cene sú TRI čísla. Keď na prvé
-- SMS nepríde, klient dostane druhé a tretie bez doplatku. Aj keby všetky tri
-- zlyhali a provider nevrátil nič, ostáva zisk (Kolumbia: tržba $0,55,
-- najhorší náklad $0,31). Bez počítadla by sa nedalo ustrážiť, koľko čísel už
-- klient minul — a štvrté by išlo z našej marže.

alter table telegram_otp_orders
  add column if not exists provider text not null default 'vrnum'
    check (provider in ('vrnum', '5sim'));

alter table telegram_otp_orders
  add column if not exists attempts_used int not null default 1
    check (attempts_used >= 1);

-- Koľko čísel bolo v cene zahrnutých. Uložené NA OBJEDNÁVKE, nie čítané z env:
-- keby sme raz limit zmenili, staré objednávky musia dobehnúť s pravidlami,
-- za ktorých klient platil.
alter table telegram_otp_orders
  add column if not exists attempts_allowed int not null default 1
    check (attempts_allowed >= 1);

-- Všetky čísla, ktoré k tejto objednávke padli. Kvôli podpore a dohľadaniu.
alter table telegram_otp_orders
  add column if not exists attempt_numbers jsonb not null default '[]'::jsonb;

comment on column telegram_otp_orders.provider is
  'Kto objednávku vybavil: vrnum alebo 5sim. Identifikátory krajín aj objednávok sa medzi nimi líšia.';
comment on column telegram_otp_orders.attempts_used is
  'Koľko čísel už klient na túto platbu dostal.';
comment on column telegram_otp_orders.attempts_allowed is
  'Koľko ich má v cene. Uložené na objednávke, aby zmena cenníka neovplyvnila už zaplatené.';

create index if not exists telegram_otp_orders_provider_idx
  on telegram_otp_orders (provider, created_at desc);

do $probe$
declare v_bez int;
begin
  select count(*) into v_bez from telegram_otp_orders where provider is null;
  if v_bez > 0 then raise exception 'otp: % objednavok bez providera', v_bez; end if;

  if exists (select 1 from telegram_otp_orders where provider <> 'vrnum') then
    raise exception 'otp: existujuca objednavka dostala ineho providera nez vrnum';
  end if;

  -- Tabuľka je service-only. Overiť, že sa na tom pridaním stĺpcov nič nezmenilo.
  if has_table_privilege('authenticated', 'public.telegram_otp_orders', 'SELECT') then
    raise exception 'otp: KLIENT VIDI OBJEDNAVKY PRIAMO';
  end if;
end $probe$;

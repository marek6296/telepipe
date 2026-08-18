-- 026 — spárovaný súkromný Telegram znamená „odpisuj mi"
--
-- PROBLÉM: `owner_as_client` (023) bol defaultne `false`, ale nič to klientovi
-- nepovedalo. Kto si spáril súkromný Telegram, čakal, že mu modelka odpíše —
-- a ona mlčala, lebo `userbot.py:198` správu od majiteľa zahodí ako povel.
-- Presne to sa stalo účtu r.brodniansky@gmail.com: súkromný chat spárovaný,
-- prepínač vypnutý, modelka nemá ako odpovedať a klient nemá ako zistiť prečo.
-- Simona a Mio ho mali roky zapnutý ručne v SQL, takže Marekovi to fungovalo
-- a klientovi nie — najhorší možný druh rozdielu.
--
-- ROZHODNUTIE: spárovanie súkromného Telegramu JE súhlas s tým, aby odpisovala.
-- Kto to chce inak (súkromný chat len ako povelový kanál), prepínač si vypne —
-- ale musí to byť jeho rozhodnutie, nie tichý default.

-- 1. Nové modelky štartujú so zapnutým. Bez `owner_chat_id` to aj tak nemá čo
--    označiť (`is_owner` sa porovnáva práve s ním), takže to nič nerozbije.
alter table models alter column owner_as_client set default true;

-- 2. Prvé spárovanie ho zapne. Trigger, nie zápis v appke, lebo `owner_chat_id`
--    píšu DVE miesta: server action v appke (ručné prepísanie) a kontrolný bot
--    vo workeri (párovací kód). Podmienka je úzka schválne — vypnutie prepínača
--    `owner_chat_id` nemení, takže sa nikomu nezapne späť za chrbtom.
create or replace function models_owner_pairing_enables_replies()
returns trigger
language plpgsql
as $$
begin
  if old.owner_chat_id is null and new.owner_chat_id is not null then
    new.owner_as_client := true;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_models_owner_pairing on models;
create trigger trg_models_owner_pairing
  before update of owner_chat_id on models
  for each row
  execute function models_owner_pairing_enables_replies();

-- 3. Dorovnanie existujúcich: kto má spárovaný súkromný chat, dostáva odpovede.
--    Týka sa to jedinej modelky (Ayko Kuro) — Simona a Mio to už majú zapnuté.
update models
   set owner_as_client = true, updated_at = now()
 where owner_chat_id is not null
   and coalesce(owner_as_client, false) = false;

-- Kontrola: žiadna spárovaná modelka nesmie ostať s vypnutým prepínačom.
do $$
declare v_zle int;
begin
  select count(*) into v_zle from models
   where owner_chat_id is not null and coalesce(owner_as_client, false) = false;
  if v_zle > 0 then
    raise exception '026: % spárovaných modeliek stále neodpisuje majiteľovi', v_zle;
  end if;
end $$;

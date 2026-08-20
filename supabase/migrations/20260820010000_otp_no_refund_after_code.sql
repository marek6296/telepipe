-- Refund po doručení SMS kódu sa odmieta.
--
-- ČO SA DALO
-- ----------
-- Kúpiť číslo, počkať na SMS, kód si opísať, zaregistrovať sa ním — a potom
-- kliknúť „Cancel & refund" a dostať coiny späť. Číslo zadarmo, opakovane.
-- Nie je to teoretická diera; klientov kamarát to tak skúsil a prešlo mu to.
--
-- Stojí to aj nás: 5sim vracia peniaze len za číslo zrušené BEZ SMS. Keď kód
-- dorazil, my sme zaplatili a klientovi by sme ešte vrátili coiny — strata na
-- oboch stranách.
--
-- KDE JE HRANICA A PREČO PRÁVE TAM
-- --------------------------------
-- Kontrola je v RPC, nie v serverovej akcii. Cez túto funkciu ide KAŽDÝ
-- refund — ručné zrušenie klientom aj automatický refund pri zlyhaní
-- providera. Jedno miesto, ktoré sa nedá obísť inou cestou v kóde. Akcia na
-- webe aj skryté tlačidlo v UI sú len pohodlie, aby človek dostal vetu
-- namiesto chyby z databázy.
--
-- Sonda overuje OBE strany: že refund po kóde padne a zostatok sa nezmení, a
-- zároveň že legitímne zrušenie bez SMS ďalej funguje. Poistka, ktorá by
-- zablokovala aj poctivé zrušenie, by bola horšia než diera.

create or replace function refund_telegram_otp_purchase(p_order uuid, p_account uuid, p_status text, p_reason text default ''::text)
returns numeric
language plpgsql security definer
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_order telegram_otp_orders;
  v_balance numeric;
begin
  if p_status is null or p_status not in ('cancelled', 'failed') then
    raise exception 'invalid refund status';
  end if;

  select * into v_order
  from telegram_otp_orders
  where id = p_order and account_id = p_account
  for update;

  if not found then raise exception 'order not found'; end if;

  -- KÓD UŽ DORAZIL = TOVAR BOL DORUČENÝ, REFUND SA NEDÁ. Viď hlavičku súboru.
  if coalesce(v_order.otp_code, '') <> '' or v_order.code_received_at is not null then
    raise exception 'refund refused: SMS code already delivered'
      using errcode = '23514';
  end if;

  select credit_balance_usd into v_balance
  from accounts where id = p_account
  for update;
  if not found then raise exception 'account not found'; end if;

  if v_order.refunded_at is not null then return v_balance; end if;

  update accounts
     set credit_balance_usd = credit_balance_usd + v_order.charged_credits
   where id = p_account
   returning credit_balance_usd into v_balance;

  update telegram_otp_orders
     set status = p_status,
         refunded_credits = charged_credits,
         refunded_at = now(),
         cancelled_at = case when p_status = 'cancelled' then now() else cancelled_at end,
         last_error = case when p_status = 'failed' then coalesce(p_reason, '') else last_error end,
         updated_at = now()
   where id = p_order;

  insert into telegram_otp_credit_events (
    order_id, account_id, account_email, kind, amount, balance_after, reason
  ) values (
    p_order, p_account, v_order.account_email, 'refund', v_order.charged_credits,
    v_balance, coalesce(nullif(p_reason, ''), p_status)
  );

  return v_balance;
end;
$function$;

do $$
declare
  v_acc uuid;
  v_order uuid := gen_random_uuid();
  v_bez_kodu uuid := gen_random_uuid();
  v_pred numeric; v_po numeric; v_po_platnom numeric;
  v_odmietnute boolean := false;
  v_reached boolean := false;
begin
  select id into v_acc from accounts order by created_at limit 1;
  if v_acc is null then
    raise notice 'otp-refund: sonda preskočená — žiadny účet';
  else
    begin
      select credit_balance_usd into v_pred from accounts where id = v_acc;

      -- (1) S doručeným kódom refund NESMIE prejsť.
      insert into telegram_otp_orders (id, idempotency_key, client_reference, account_id,
        account_email, service, country_code, country_name, status, provider,
        provider_price_usd, charged_credits, otp_code, code_received_at)
      values (v_order, gen_random_uuid(), 'probe', v_acc, 'probe@test', 'telegram', 'usa',
              'United States', 'code_received', '5sim', 0.85, 2.55, '12345', now());
      begin
        perform refund_telegram_otp_purchase(v_order, v_acc, 'cancelled', 'probe');
      exception when check_violation then v_odmietnute := true;
      end;
      select credit_balance_usd into v_po from accounts where id = v_acc;

      -- (2) Bez kódu refundovať MUSÍ ďalej — poistka nesmie zablokovať
      --     poctivé zrušenie, keď SMS naozaj nedorazila.
      insert into telegram_otp_orders (id, idempotency_key, client_reference, account_id,
        account_email, service, country_code, country_name, status, provider,
        provider_price_usd, charged_credits)
      values (v_bez_kodu, gen_random_uuid(), 'probe2', v_acc, 'probe@test', 'telegram', 'usa',
              'United States', 'waiting', '5sim', 0.85, 2.55);
      perform refund_telegram_otp_purchase(v_bez_kodu, v_acc, 'cancelled', 'probe');
      select credit_balance_usd into v_po_platnom from accounts where id = v_acc;

      v_reached := true;
      raise exception 'otp-refund-probe-rollback';
    exception when others then
      if sqlerrm <> 'otp-refund-probe-rollback' then raise; end if;
    end;

    if not v_reached then raise exception 'otp-refund: sonda nedobehla'; end if;
    if not v_odmietnute then
      raise exception 'otp-refund: refund po doručení kódu PREŠIEL — diera je stále otvorená';
    end if;
    if v_po <> v_pred then
      raise exception 'otp-refund: zostatok sa zmenil (% -> %), hoci refund mal padnúť', v_pred, v_po;
    end if;
    if v_po_platnom <> v_pred + 2.55 then
      raise exception 'otp-refund: legitímny refund bez kódu neprešiel (% -> %)', v_pred, v_po_platnom;
    end if;
  end if;

  raise notice 'otp-refund: po kóde odmietnuté, bez kódu funguje — OK';
end $$;

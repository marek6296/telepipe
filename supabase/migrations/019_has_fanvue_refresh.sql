-- Fáza 3.x — „mám ešte čím obnovovať?" bez toho, aby token opustil DB.
--
-- PREČO
-- -----
-- Prístupový token z Fanvue žije hodinu a `fanvue_api._access_token` ho obnovuje
-- lenivo — teda len keď sa naozaj volá ich API. Modelke s pripojeným, ale
-- vypnutým agentom (`fanvue.enabled = false`) ho teda neobnovoval nikto a
-- v dashboarde svietilo červené „Access token expires — 1 min ago", hoci
-- pripojenie bolo v poriadku. Marek to skúšal opraviť opätovným pripojením;
-- vydržalo to presne hodinu.
--
-- Worker si po novom token obnovuje sám (`fanvue_tenant.FanvueSupervisor`), ale
-- dashboard potrebuje vedieť ešte jednu vec: či vôbec MÁ čím obnovovať. To je
-- rozdiel medzi „o chvíľu sa obnoví" a „účet treba pripojiť znova" — a bez toho
-- sa nedá napísať ani jedna z tých viet pravdivo.
--
-- Na `refresh_token_enc` klient grant nemá a mať nebude (migrácia 011), preto
-- von ide jediný bit. Tvar je doslova `has_eleven_key` (migrácia 014):
-- security definer + kontrola vlastníctva ako prvá vec vo funkcii, `stable`,
-- pevný `search_path` a žiadne právo pre `public`/`anon`.

create or replace function has_fanvue_refresh(p_model uuid)
returns boolean language plpgsql stable security definer
set search_path = public, pg_temp as $$
declare v_has boolean;
begin
  if not exists (
    select 1 from models m where m.id = p_model and m.account_id = (select auth.uid())
  ) then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  select coalesce(f.refresh_token_enc, '') <> '' into v_has
  from fanvue f where f.model_id = p_model;

  return coalesce(v_has, false);
end;
$$;

revoke execute on function has_fanvue_refresh(uuid) from public, anon;
grant execute on function has_fanvue_refresh(uuid) to authenticated;

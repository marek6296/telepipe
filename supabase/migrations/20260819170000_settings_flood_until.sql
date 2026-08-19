-- Flood pauza oddelená od ručnej pauzy.
--
-- PROBLÉM
-- -------
-- `settings.ai_paused` niesol dve úplne rozdielne veci:
--   1. „majiteľ vypol odpovedanie"   — smie sa zrušiť klikom v menu
--   2. „Telegram nás označil za spam" — NESMIE sa zrušiť klikom v menu
-- `set_tg_reply_mode('auto')` zhadzuje `ai_paused`, čím ticho rušil aj
-- 24-hodinovú ochranu po `PeerFloodError` — a účet sa rozbehol priamo do
-- spam-flagu. Význam (1) je správny a ostáva; význam (2) dostáva vlastný
-- stĺpec, ktorého sa prepnutie režimu nedotkne.
--
-- POZOR NA GRANT
-- --------------
-- `settings` mala TABLE-LEVEL grant `authenticated=arwd`. Table grant sa
-- automaticky vzťahuje aj na každý NOVÝ stĺpec, takže `flood_until` by bol
-- klientom zapisovateľný — čiže by si flood pauzu vedel zrušiť sám. Preto sa
-- grant mení na column-scoped (rovnaký postup ako migrácia 017 pri `accounts`).
-- Column-level REVOKE by nestačil: table grant ho prebije.

alter table settings add column if not exists flood_until timestamptz;

comment on column settings.flood_until is
  'Do kedy nič neposielať po flood chybe od Telegramu (PeerFloodError = 24 h). '
  'Oddelené od ai_paused zámerne: ai_paused je ručná pauza majiteľa a smie ju '
  'zrušiť prepnutie režimu, túto NIE. Ruší ju výhradne worker po uplynutí času.';

revoke all on settings from authenticated;

-- Presne to, čo web používa (overené grepom): číta režim + pauzu, zapisuje
-- pauzu a režim. `flood_until` je ČITATEĽNÝ (nech vie ukázať „pauza beží"),
-- ale NEZAPISOVATEĽNÝ.
grant select (model_id, ai_paused, tg_reply_mode, tg_fallback_minutes, flood_until)
  on settings to authenticated;
grant update (ai_paused, tg_reply_mode, tg_fallback_minutes) on settings to authenticated;
grant insert (model_id, ai_paused, tg_reply_mode, tg_fallback_minutes) on settings to authenticated;
grant delete on settings to authenticated;

do $probe$
declare
  v_model uuid;
  v_write_blocked boolean := false;
  v_can_read boolean;
  v_can_pause boolean;
  v_can_mode boolean;
  v_before timestamptz; v_after timestamptz;
begin
  select model_id into v_model from settings limit 1;
  if v_model is null then
    raise notice 'flood_until: sonda preskocena — ziadne settings';
    return;
  end if;

  v_write_blocked := not has_column_privilege('authenticated', 'public.settings', 'flood_until', 'UPDATE');
  v_can_read := has_column_privilege('authenticated', 'public.settings', 'flood_until', 'SELECT');
  v_can_pause := has_column_privilege('authenticated', 'public.settings', 'ai_paused', 'UPDATE');
  v_can_mode := has_column_privilege('authenticated', 'public.settings', 'tg_reply_mode', 'UPDATE')
            and has_column_privilege('authenticated', 'public.settings', 'tg_fallback_minutes', 'UPDATE');

  begin
    update settings set flood_until = now() + interval '24 hours' where model_id = v_model;
    select flood_until into v_before from settings where model_id = v_model;
    update settings set tg_reply_mode = 'auto', ai_paused = false where model_id = v_model;
    select flood_until into v_after from settings where model_id = v_model;

    if not v_write_blocked then raise exception 'flood_until: KLIENT SI VIE ZRUSIT FLOOD PAUZU'; end if;
    if not v_can_read then raise exception 'flood_until: klient ju ani nevidi'; end if;
    if not v_can_pause then raise exception 'flood_until: web uz nevie prepnut ai_paused'; end if;
    if not v_can_mode then raise exception 'flood_until: web uz nevie prepnut rezim odpovedania'; end if;
    if v_before is distinct from v_after then
      raise exception 'flood_until: prepnutie rezimu ju zmenilo';
    end if;

    raise exception 'flood-sonda-rollback' using errcode = 'P0001';
  exception when raise_exception then
    null;
  end;

  if exists (select 1 from settings where flood_until is not null) then
    raise exception 'flood_until: sonda po sebe nechala zapnutu pauzu';
  end if;
end $probe$;

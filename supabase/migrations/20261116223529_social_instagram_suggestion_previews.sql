-- Render intent markers for review. Authorization, offer/window/URL quotas and
-- exact immutable command text are still checked by the existing send boundary.
create function public.social_render_instagram_text(p_text text,p_cfg public.instagram) returns text
language plpgsql immutable set search_path=public,pg_temp as $$
declare value text:=regexp_replace(coalesce(p_text,''),'^\s+|\s+$','','g'); markers text[]; marker text; target text; destination text;
begin
  select array_agg(m[1]) into markers from regexp_matches(value,'\[\[(LINK|TELEGRAM|LINKPAGE|HIGHLIGHTS|REMIND|PHOTO)\]\]','g') m;
  if coalesce(array_length(markers,1),0)>1 then return null; end if;
  marker:=markers[1];
  if marker='PHOTO' then return null; end if;
  if marker in ('REMIND','HIGHLIGHTS') then value:=replace(value,'[['||marker||']]','');
  elsif marker in ('LINK','TELEGRAM','LINKPAGE') then
    target:=case marker when 'TELEGRAM' then 'telegram' when 'LINKPAGE' then 'bio_link' else case when p_cfg.funnel_target='both' then 'telegram' else p_cfg.funnel_target end end;
    if p_cfg.funnel_target not in (target,'both') then return null; end if;
    if target='telegram' then
      destination:=ltrim(btrim(p_cfg.telegram_handle),'@');
      if destination!~'^[a-zA-Z][a-zA-Z0-9_]{4,31}$' then return null; end if;
      destination:='https://t.me/'||destination;
    elsif target='bio_link' then
      destination:=btrim(p_cfg.bio_link);
      if destination!~'^https://(www\.)?linkovne\.com(:443)?/[^/?#[:space:]][^[:space:]]*$' then return null; end if;
    else return null; end if;
    value:=replace(value,'[['||marker||']]',destination);
  end if;
  if value like '%[[%' or value like '%]]%' then return null; end if;
  return nullif(regexp_replace(value,'^\s+|\s+$','','g'),'');
end $$;

create function public.social_instagram_previews(p_model uuid,p_suggestions jsonb) returns jsonb
language sql stable security definer set search_path=public,pg_temp as $$
  select coalesce(jsonb_agg(social_render_instagram_text(v.value,cfg) order by v.ordinality),'[]'::jsonb)
  from instagram cfg cross join lateral jsonb_array_elements_text(p_suggestions) with ordinality v
  where cfg.model_id=p_model;
$$;
revoke all on function public.social_render_instagram_text(text,public.instagram),public.social_instagram_previews(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.social_render_instagram_text(text,public.instagram),public.social_instagram_previews(uuid,jsonb) to service_role;

-- Keep the original draft array immutable, but approve its displayed rendering.
-- command.text then freezes the exact visible URL/text, even if settings change.
do $$
declare definition text; previous text:=$old$if p_operation='approve' and not(p.suggestions @> jsonb_build_array(c.text)) then$old$;
begin
  select pg_get_functiondef('public.social_enqueue(uuid,uuid,uuid,text,text,text,text,uuid,jsonb,text,uuid,timestamptz,text,text)'::regprocedure) into definition;
  if strpos(definition,previous)=0 then raise exception 'social_enqueue approval guard changed; review migration'; end if;
  execute replace(definition,previous,$new$if p_operation='approve' and not(p.suggestions @> jsonb_build_array(c.text))
    and not(p_channel='instagram' and exists(select 1 from instagram cfg cross join lateral jsonb_array_elements_text(p.suggestions) v
      where cfg.model_id=p_model and social_render_instagram_text(v.value,cfg)=c.text)) then$new$);
end $$;

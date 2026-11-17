-- Counts are derived from real conversation history. Reading this function or
-- opening a chat never changes state and never sends a provider read receipt.
create function public.social_waiting_message_counts(p_model uuid,p_owner uuid,p_contacts jsonb)
returns jsonb language plpgsql stable security definer set search_path=public,pg_temp as $$
declare c jsonb; tab text; ext text; stamp text; scope_filter text; assistant_scope text; n bigint; result jsonb:='{}';
begin
 if not exists(select 1 from models where id=p_model and account_id=p_owner) then raise exception 'owner_required'; end if;
 if jsonb_typeof(p_contacts)<>'array' or jsonb_array_length(p_contacts)>100 then raise exception 'invalid_contacts'; end if;
 for c in select value from jsonb_array_elements(p_contacts) loop
  tab:=case c->>'channel' when 'telegram' then 'dm_messages' when 'instagram' then 'ig_messages' when 'fanvue' then 'fv_messages' end;
  if tab is null then continue; end if;
  ext:=case c->>'channel' when 'telegram' then 'tg_id' when 'instagram' then 'igsid' else 'fan_uuid' end;
  stamp:=case c->>'channel' when 'telegram' then 'created_at' else 'occurred_at' end;
  scope_filter:=case c->>'channel' when 'telegram' then ' and u.account_scope in ('''',$3)' else '' end;
  assistant_scope:=case c->>'channel' when 'telegram' then ' and a.account_scope in ('''',$3)' else '' end;
  -- Compare original provider chronology, not import IDs: a late import of an
  -- older reply must not hide newer incoming messages. Unknown times sort first.
  execute format('select count(*) from %I u where u.model_id=$1 and u.%I::text=$2 and u.role=''user'' %s and not exists(select 1 from %I a where a.model_id=$1 and a.%I::text=$2 and a.role=''assistant'' %s and (coalesce(a.%I,''-infinity''::timestamptz),a.id)>(coalesce(u.%I,''-infinity''::timestamptz),u.id))',tab,ext,scope_filter,tab,ext,assistant_scope,stamp,stamp)
    into n using p_model,c->>'externalId',c->>'accountScope';
  result:=result||jsonb_build_object((c->>'channel')||':'||(c->>'externalId'),n);
 end loop;
 return result;
end $$;
revoke all on function public.social_waiting_message_counts(uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.social_waiting_message_counts(uuid,uuid,jsonb) to service_role;

-- Operator briefs are independent from the persona's conversational memory.
create table public.social_person_briefs (
  model_id uuid not null references public.models(id) on delete cascade,
  cache_key text not null check(length(cache_key)=64),
  summary text not null default '', coverage text not null default '', truncated boolean not null default false,
  generated_at timestamptz,
  lease_token uuid, lease_until timestamptz,
  primary key(model_id,cache_key)
);
alter table public.social_person_briefs enable row level security;
revoke all on public.social_person_briefs from public,anon,authenticated;
grant all on public.social_person_briefs to service_role;

create function public.social_claim_person_brief(p_model uuid,p_key text,p_refresh boolean default false)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare item social_person_briefs; token uuid:=gen_random_uuid();
begin
  insert into social_person_briefs(model_id,cache_key) values(p_model,p_key) on conflict do nothing;
  update social_person_briefs set lease_token=token,lease_until=now()+interval '10 minutes'
    where model_id=p_model and cache_key=p_key and (lease_until is null or lease_until<now())
    and (generated_at is null or (p_refresh and generated_at<now()-interval '30 seconds'))
    returning * into item;
  if found then return jsonb_build_object('claimed',true,'item',to_jsonb(item)); end if;
  select * into item from social_person_briefs where model_id=p_model and cache_key=p_key;
  return jsonb_build_object('claimed',false,'item',to_jsonb(item));
end $$;
revoke all on function public.social_claim_person_brief(uuid,text,boolean) from public,anon,authenticated;
grant execute on function public.social_claim_person_brief(uuid,text,boolean) to service_role;

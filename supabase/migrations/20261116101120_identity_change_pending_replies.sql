-- A proposal generated from an old identity group must not survive its correction.
-- Cover both sides and all channels, including changes made through owner RPCs.
create function public.conversation_invalidate_proposals() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
begin
  update pending_replies p set status='superseded'
    where p.model_id=new.model_id and p.status='awaiting' and exists (
      select 1 from conversation_identities i
      where i.model_id=new.model_id
        and (i.id=new.id or i.person_id in (old.person_id,new.person_id))
        and p.channel=i.platform
        and (p.conv_key=i.external_id or
          (i.platform='instagram' and split_part(p.conv_key,':',1)=i.external_id))
    );
  return new;
end $$;
create trigger conversation_invalidate_proposals
  after update of person_id,status,candidate_id on public.conversation_identities
  for each row when (old.person_id is distinct from new.person_id
    or old.status is distinct from new.status or old.candidate_id is distinct from new.candidate_id)
  execute function public.conversation_invalidate_proposals();
revoke all on function public.conversation_invalidate_proposals() from public,anon,authenticated;

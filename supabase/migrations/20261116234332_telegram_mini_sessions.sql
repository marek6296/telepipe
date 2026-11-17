-- Dedicated Social-only Telegram sessions. Never a Supabase login/token.
create table public.telegram_mini_sessions (
  token_hash text primary key check(token_hash ~ '^[0-9a-f]{64}$'),
  bot_model_id uuid not null references public.models(id) on delete cascade,
  account_id uuid not null references public.accounts(id) on delete cascade,
  telegram_owner_id bigint not null check(telegram_owner_id>0),
  bot_fingerprint text not null,
  init_hash text not null check(init_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now()+interval '30 minutes',
  revoked_at timestamptz,
  unique(bot_model_id,init_hash)
);
alter table public.telegram_mini_sessions enable row level security;
revoke all on public.telegram_mini_sessions from public,anon,authenticated;
grant all on public.telegram_mini_sessions to service_role;
create index telegram_mini_sessions_created on public.telegram_mini_sessions(created_at);

create function public.telegram_mini_issue(p_bot uuid,p_account uuid,p_owner bigint,p_fingerprint text,p_init text,p_token text,p_auth_date timestamptz)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare m models; s telegram_mini_sessions;
begin
  if p_auth_date is null or p_auth_date<now()-interval '5 minutes' or p_auth_date>now()+interval '30 seconds'
    or p_token is null or p_token !~ '^[0-9a-f]{64}$' or p_init is null or p_init !~ '^[0-9a-f]{64}$' then return null; end if;
  select * into m from models where id=p_bot for share;
  if not found or m.account_id is distinct from p_account or m.owner_chat_id is distinct from p_owner
    or coalesce(m.owner_chat_id,0)<=0 or coalesce(m.control_bot_token_enc,'')=''
    or md5(m.control_bot_token_enc) is distinct from p_fingerprint then return null; end if;
  -- Replay records outlive both initData and the maximum session lifetime.
  delete from telegram_mini_sessions where created_at<now()-interval '1 day';
  insert into telegram_mini_sessions(token_hash,bot_model_id,account_id,telegram_owner_id,bot_fingerprint,init_hash)
    values(p_token,p_bot,p_account,p_owner,p_fingerprint,p_init) on conflict do nothing returning * into s;
  if not found then return null; end if;
  return jsonb_build_object('bot_model_id',s.bot_model_id,'account_id',s.account_id,'telegram_owner_id',s.telegram_owner_id,
    'init_hash',s.init_hash,'created_at',s.created_at,'expires_at',s.expires_at);
end $$;

create function public.telegram_mini_session(p_token text) returns jsonb
language sql stable security definer set search_path=public,pg_temp as $$
  select jsonb_build_object('bot_model_id',s.bot_model_id,'account_id',s.account_id,'telegram_owner_id',s.telegram_owner_id,
    'init_hash',s.init_hash,'created_at',s.created_at,'expires_at',s.expires_at)
  from telegram_mini_sessions s join models m on m.id=s.bot_model_id
  where s.token_hash=p_token and s.revoked_at is null and s.expires_at>now() and s.created_at>now()-interval '8 hours'
    and m.account_id=s.account_id and m.owner_chat_id=s.telegram_owner_id and coalesce(m.control_bot_token_enc,'')<>''
    and md5(m.control_bot_token_enc)=s.bot_fingerprint;
$$;

create function public.telegram_mini_refresh(p_token text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare s telegram_mini_sessions;
begin
  update telegram_mini_sessions x set expires_at=least(now()+interval '30 minutes',x.created_at+interval '8 hours')
    from models m where x.token_hash=p_token and m.id=x.bot_model_id and x.revoked_at is null
    and x.expires_at>now() and x.created_at>now()-interval '8 hours'
    and m.account_id=x.account_id and m.owner_chat_id=x.telegram_owner_id
    and coalesce(m.control_bot_token_enc,'')<>'' and md5(m.control_bot_token_enc)=x.bot_fingerprint returning x.* into s;
  if not found then return null; end if;
  return jsonb_build_object('expires_at',s.expires_at);
end $$;

-- Revocation remains recorded even when an owner/token is later switched back.
create function public.telegram_mini_revoke_pairing() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
begin
  if old.owner_chat_id is distinct from new.owner_chat_id or old.account_id is distinct from new.account_id
    or old.control_bot_token_enc is distinct from new.control_bot_token_enc then
    update telegram_mini_sessions set revoked_at=now() where bot_model_id=new.id and revoked_at is null;
  end if;
  return new;
end $$;
create trigger telegram_mini_revoke_pairing after update of owner_chat_id,account_id,control_bot_token_enc on public.models
  for each row execute function public.telegram_mini_revoke_pairing();

revoke all on function public.telegram_mini_issue(uuid,uuid,bigint,text,text,text,timestamptz) from public,anon,authenticated;
revoke all on function public.telegram_mini_session(text) from public,anon,authenticated;
revoke all on function public.telegram_mini_refresh(text) from public,anon,authenticated;
revoke all on function public.telegram_mini_revoke_pairing() from public,anon,authenticated;
grant execute on function public.telegram_mini_issue(uuid,uuid,bigint,text,text,text,timestamptz) to service_role;
grant execute on function public.telegram_mini_session(text) to service_role;
grant execute on function public.telegram_mini_refresh(text) to service_role;

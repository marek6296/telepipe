-- Telepipe core: účty, modely (tenanti), ledger, cenník, lease RPC.
create extension if not exists pgcrypto;

create table accounts (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  credit_balance_usd numeric not null default 0,
  created_at timestamptz not null default now()
);

create table models (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  name text not null default '',
  status text not null default 'draft'
    check (status in ('draft','active','paused','error','disabled')),
  status_reason text not null default '',
  claimed_by text,
  heartbeat_at timestamptz,
  tg_api_id int,
  tg_api_hash text not null default '',
  tg_session_enc text not null default '',
  control_bot_token_enc text not null default '',
  owner_chat_id bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index models_claim_idx on models (status, claimed_by, heartbeat_at);

create table usage_events (
  id bigint generated always as identity primary key,
  model_id uuid not null references models(id) on delete cascade,
  account_id uuid not null references accounts(id) on delete cascade,
  kind text not null check (kind in ('chat','summary','vision','audio','voice')),
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  unit_count int not null default 0,
  atlas_cost_usd numeric not null,
  charged_usd numeric not null,
  created_at timestamptz not null default now()
);
create index usage_events_model_time_idx on usage_events (model_id, created_at desc);
create index usage_events_account_time_idx on usage_events (account_id, created_at desc);

create table pricing (
  model_slug text primary key,
  input_usd_per_mtok numeric not null default 0,
  output_usd_per_mtok numeric not null default 0,
  multiplier numeric not null default 2.0
);
insert into pricing (model_slug, input_usd_per_mtok, output_usd_per_mtok) values ('_default', 0, 0);

-- Lease: atomicky si replika zoberie voľných/opustených tenantov.
create or replace function claim_models(p_replica text, p_capacity int)
returns setof models language sql security definer as $$
  update models m set claimed_by = p_replica, heartbeat_at = now()
  where m.id in (
    select id from models
    where status = 'active'
      and (claimed_by is null or heartbeat_at < now() - interval '90 seconds')
      and (claimed_by is distinct from p_replica)
    order by created_at
    for update skip locked
    limit p_capacity
  )
  returning m.*;
$$;

create or replace function heartbeat_models(p_replica text)
returns void language sql security definer as $$
  update models set heartbeat_at = now() where claimed_by = p_replica;
$$;

create or replace function release_models(p_replica text)
returns void language sql security definer as $$
  update models set claimed_by = null where claimed_by = p_replica;
$$;

create or replace function release_model(p_model uuid)
returns void language sql security definer as $$
  update models set claimed_by = null where id = p_model;
$$;

-- Ledger + odpočet kreditu v jednej transakcii.
create or replace function record_usage(
  p_model uuid, p_kind text,
  p_input_tokens int, p_output_tokens int, p_unit_count int,
  p_atlas_cost_usd numeric, p_charged_usd numeric
) returns numeric language plpgsql security definer as $$
declare v_account uuid; v_balance numeric;
begin
  select account_id into v_account from models where id = p_model;
  insert into usage_events (model_id, account_id, kind, input_tokens,
    output_tokens, unit_count, atlas_cost_usd, charged_usd)
  values (p_model, v_account, p_kind, p_input_tokens, p_output_tokens,
    p_unit_count, p_atlas_cost_usd, p_charged_usd);
  update accounts set credit_balance_usd = credit_balance_usd - p_charged_usd
  where id = v_account
  returning credit_balance_usd into v_balance;
  return v_balance;
end;
$$;

create or replace function credit_balance(p_model uuid)
returns numeric language sql security definer as $$
  select a.credit_balance_usd from accounts a
  join models m on m.account_id = a.id where m.id = p_model;
$$;

alter table accounts enable row level security;
alter table models enable row level security;
alter table usage_events enable row level security;
alter table pricing enable row level security;

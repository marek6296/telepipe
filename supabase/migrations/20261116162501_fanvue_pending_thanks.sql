-- Reconciled unlocks may be observed without a payment webhook. Preserve the
-- thank-you independently of bought_count and of the source event's lifetime.
alter table public.fv_users
  add column pending_thanks boolean not null default false;

create index fv_users_pending_thanks_idx
  on public.fv_users (model_id, fan_uuid) where pending_thanks;

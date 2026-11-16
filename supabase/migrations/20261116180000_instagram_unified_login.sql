-- Server-only metadata; tokens remain encrypted. NULL expiry means no scheduled expiration.
alter table public.instagram
  add column if not exists token_type text not null default 'instagram' check (token_type in ('instagram','unified')),
  add column if not exists client_business_id text not null default '',
  add column if not exists login_config_id text not null default '';
comment on column public.instagram.token_expires_at is 'NULL for non-expiring Unified Login SUAT; legacy Instagram User tokens expire and need refresh.';
-- Existing column grants must not expose server-only metadata.
revoke select (client_business_id, login_config_id, token_type) on public.instagram from anon, authenticated;

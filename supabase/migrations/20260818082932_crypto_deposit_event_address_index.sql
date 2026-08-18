-- Supports the foreign-key lookup used when a permanent deposit address is
-- retired or audited. This index is intentionally limited to the new crypto
-- deposit subsystem.
create index crypto_deposit_events_address_id_idx
  on public.crypto_deposit_events (deposit_address_id);

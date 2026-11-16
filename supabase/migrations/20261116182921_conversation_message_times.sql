-- A provider timestamp is not the time we happened to import a conversation.
-- Legacy rows stay unknown until reconciled with their actual provider UUID.
alter table public.fv_messages add column if not exists occurred_at timestamptz;
comment on column public.fv_messages.occurred_at is
  'Actual provider sentAt (or locally confirmed send time). NULL means unknown; created_at is ingestion time.';

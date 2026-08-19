-- Chýbajúce indexy na cudzích kľúčoch tabuliek z vrstiev 1–3 (nález z
-- Supabase performance advisora).
--
-- `chat_messages.sender_id` je z nich jediný, ktorý naozaj zabolí: pozerá sa naň
-- RLS aj `chat_display_names()` pri každom načítaní miestnosti, a Community
-- rastie všetkým naraz. Zvyšok sú lacné poistky na stĺpce, ktoré sa čítajú zriedka.

create index if not exists chat_messages_sender_idx on chat_messages (sender_id);
create index if not exists chat_messages_deleted_by_idx on chat_messages (deleted_by) where deleted_by is not null;
create index if not exists chat_reads_account_idx on chat_reads (account_id);
create index if not exists chat_mutes_muted_by_idx on chat_mutes (muted_by) where muted_by is not null;
create index if not exists access_requests_decided_by_idx on access_requests (decided_by) where decided_by is not null;

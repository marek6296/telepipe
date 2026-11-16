# Social sites — shared operator workspace

## Intent and approach

Add Social sites immediately after Voice for persona models. Keep existing channel
tabs for connection/settings. The new page is the daily workspace: connected
channels and modes, people grouped by verified shared identities, real histories,
current suggestions, explicit manual replies, and identity/takeover management.
UI stays English and follows the existing dark monochrome app.

The owner has delegated implementation choices in this project. Chosen approach:
reuse the existing Next.js app, Supabase records and one live tenant worker. A new
durable operator command queue delivers web actions to the existing senders.
Direct provider calls from Vercel would duplicate delivery gates and cannot safely
reuse Telegram's session; a separate messaging engine would split context and
approvals. Neither fits. Existing bot and web share pending_replies and identity
state; either interface may resolve a draft exactly once.

## Experience

- Three compact channel cards: connection/handle, Manual/Semi/Auto, current sync
  and a link to existing connection/settings pages. Worker state and shared LA
  schedule remain visible. Manual maps to automation Off but allows explicit
  operator messages. Turning modes does not restart Telegram sessions.
- Inbox: search, All / Needs reply / Approvals / Manual filters and channel filter;
  grouped people, channel badges, latest preview/time and waiting count. Pagination
  must not silently discard older people. Candidate matches remain separate.
- Conversation: linked account selector, channel clearly shown, original messages
  with source times, older-history loading; optional combined timeline is read-only
  until a specific sending account is selected. Unknown provider times stay unknown.
- Semi: current draft alternatives, approve exact text, regenerate or brief, skip.
  A custom composer sends exact operator text. Queued/working/sent/failed/uncertain
  are distinct; double clicks and HTTP retries use the same request UUID.
- Person panel: linked accounts, context summary, per-account AI takeover/resume,
  confirm candidate/pick another account, and separate a wrong match. Linking
  explicitly explains that private history will be shared; it is audited and
  invalidates old drafts and queued context decisions.
- Refresh via authenticated read-only polling (5 seconds while visible, refresh on
  focus and after actions), without generating drafts, provider reads or seen.
- Responsive: full inbox on desktop, list/conversation navigation on mobile;
  clear loading, empty, disconnected, stale, failure and offline states.

## Boundaries

Every read/action independently authorizes the model. Service-role reads expose
only explicit DTO fields (never tokens, prompts, raw settings or debug payloads).
Existing Instagram superadmin rollout remains enforced inside the unified page.
Cross-model IDs, foreign pending rows, unsupported channels and stale versions fail
closed. New tables/RPCs revoke default public/anon/authenticated writes.

Manual commands bypass only automation mode/schedule and per-contact takeover.
Keep connection/account scope, active worker lease, emergency/flood pause, send
quotas, contact restrictions and Instagram messaging window. No seen until the
actual send boundary. Manual sending in an automatic conversation takes over that
conversation before sending; Semi custom answers retain Semi for the next input.

Do not replay uncertain provider sends. Preserve immutable command text, source,
identity version and expected suggestions; mark the external-send boundary in DB
before the call. Worker restarts retry safe work only. Approved Instagram actions
continue through the existing durable reservation pipeline.

This adds management of current messaging integrations, not a public-post scheduler,
new media generation, payments, or unsupported Instagram APIs. Existing media are
shown when stored metadata supports them; text sending and all approval controls
must be functional, not placeholder buttons.

## Shared backend contract

`social_commands` is tenant scoped, service-write only. Columns: id/model_id,
requested_by, idempotency_key UUID; operation (`approve`,`regenerate`,`send_text`),
channel, external_id, account_scope; pending_id nullable, expected_suggestions JSONB
nullable, expected_source_id text nullable, identity_id/identity_updated_at nullable;
text/brief; status (`queued`,`working`,`sending`,`done`,`blocked`,`stale`,`failed`,
`uncertain`), lease_token/lease_until, attempts, result JSONB, reason, timestamps.
Unique (model_id,idempotency_key). A repeated key with different intent is rejected.

The web intent also freezes `expectedAccountScope`. Delivery scope is the current
Instagram account ID, `fanvue:<creator_uuid>`, or `telegram:<session fingerprint>`;
the fingerprint is computed from the stored encrypted session, never its plaintext.
Telegram additionally checks the immutable scope of its actual running client.
Shared identity rows retain their existing `primary` scope for TG/FV. Timeline
previews use provider timestamps; the context version (`last_message_id`) uses the
maximum stored row ID so even late/unknown-time imports invalidate old approvals.

RPC interfaces (all service-only, model ownership checked when enqueueing):

- `social_enqueue(p_model uuid,p_requested_by uuid,p_key uuid,p_operation text,
  p_channel text,p_external text,p_scope text,p_pending uuid,p_suggestions jsonb,
  p_source text,p_identity uuid,p_identity_updated_at timestamptz,p_text text,
  p_brief text) -> jsonb command`.
- `social_claim(p_model uuid,p_worker text) -> jsonb command or null`: fence against
  the live model lease, lease safe queued work. Expired sending becomes uncertain;
  expired working may be retried. One working/sending command per contact.
- `social_start_send(p_model uuid,p_command uuid,p_lease uuid,p_worker text)
  -> jsonb command or null`: atomically recheck lease/source/identity and, for a
  pending reply, status and expected suggestions; claim pending and record sending.
- `social_finish(p_model uuid,p_command uuid,p_lease uuid,p_status text,p_result jsonb,
  p_reason text) -> boolean`: fenced transition; safe failures restore only this
  command's claimed draft. Add pending_replies.decision_command_id for ownership.
- `social_replace_suggestions(p_model uuid,p_pending uuid,p_expected jsonb,
  p_suggestions jsonb,p_hint text,p_command uuid default null,p_lease uuid default
  null,p_worker text default null) -> boolean`: awaiting + expected-array CAS and
  updated_at. Keep canonical array comparisons, not language-specific hash encodings.
- `social_skip_pending(p_model uuid,p_pending uuid,p_expected jsonb) -> boolean`:
  exact awaiting/unclaimed draft CAS; Instagram terminal skip prevents recovery replay.
- `social_set_takeover(p_model uuid,p_channel text,p_external text,p_takeover boolean)
  -> boolean`: explicit state, invalidate unapproved drafts/automatic actions on
  takeover; never toggle or silently resume.

`social_contact_summaries` service-only view (security_invoker) unions TG/FV/IG:
model_id, channel, external_id, account_scope, identity_id, person_id,
identity_status, candidate_id, identity_updated_at, display_name, username,
avatar_url, ai_enabled, human_takeover, summary, spent_cents, last_incoming_at,
last_reply_at, last_message_id (table row id as text), last_message_role,
last_message_text, last_message_at (source time, nullable), last_activity_at.

`social_inbox(p_model uuid,p_search text,p_channel text,p_filter text,p_limit int,
p_offset int,p_allow_instagram boolean) -> jsonb {contacts: summary[], total: int}`:
page by grouped person (identity person_id or channel:external_id fallback), return
all contacts of each selected group. Filters all/needs_reply/approvals/manual. Search
one linked account includes its group. Channel gating applies before grouping.

The server loads messages directly with an explicit select for the chosen contact,
50 older at a time; pending drafts and commands via explicit model/contact filters.
No need to backfill identities during read: legacy contacts get a stable local group
and are ensured through conversation_ensure_identity only on explicit link/send.

## Verification

Meaningful tests for cross-tenant reads/actions, SQL RLS/grants, duplicate requests,
web-vs-bot claim races, fresh source/identity/draft checks, headless drafts, Manual
on all channels, quota/24h/flood gates, provider timeout uncertainty and restart.
UI checks: linked/unlinked groups, empty/disconnected/loading/error states, switching
contacts without draft leakage, poll cleanup, mobile layout, keyboard submission,
queued vs sent. Run full worker, SQL contracts, web lint/typecheck/build, then deploy
the migration, web and pinned worker with live owner read-only verification.

# Social media playback and Telegram Mini App

## Intent
The owner can understand incoming voice/video messages in Social sites and can
operate the same inbox inside Telegram without a second login or the full website.
The user delegated implementation/design choices; build on the existing inbox.

## Approach
Reuse the existing Social workspace and durable command pipeline with a compact
Mini App shell. A separate replica of the inbox would drift; embedding the full
/app route would retain irrelevant navigation and browser-login dependence.
Keep media private in Supabase Storage with owner-authorized short-lived playback
URLs. Persist typed transcripts/descriptions/status independently of display text.
Raw provider URLs alone expire and cannot provide reliable replay.

## Contracts and boundaries
- Mini App verifies Telegram initData HMAC, timestamp and exact paired owner using
  the selected model bot token. Model hint is untrusted until verified. Session is
  restricted to Social APIs/models owned by that account; it is not a full Supabase
  login. Re-pairing/disconnection invalidates access. Reject replay/forgery/foreign
  models. Web authentication remains unchanged.
- /mini is a standalone mobile shell: model picker -> inbox -> conversation,
  Telegram BackButton, safe areas, keyboard-aware composer, modes and proposals.
  Reuse all delivery/idempotency/freshness safeguards. No billing/persona/settings
  navigation in the shell. Menu button in each paired control bot opens /mini.
- Media can include multiple attachments; use private storage, service-only writes,
  strict size/time/type/network bounds, no raw tokens or client credentials. Signed
  playback URLs are short-lived. Reading/playing must never send a seen receipt.
- Audio shows player + transcript; video shows player + audio transcript + visual
  description. Explicit processing/unavailable/error states, no fabricated analysis.
  Use existing AI provider/config/billing and persist results so owner and agent see
  the same analysis. Guard stale drafts after analysis alters their context.
- Fresh/new incoming media supported on all channels; recover accessible recent
  provider media, but do not promise to recover expired historical source files.

## Validation
Auth forged/stale/replayed/wrong-bot/unpaired/foreign-account cases; private media
ownership, SSRF/oversize/timeouts; media retry/dedup and failed analysis; existing
reply protections; phone layout and Telegram initData bootstrap. No customer test
messages or seen receipts. Deploy tested SQL then pinned worker and web, verify
production and record release in the existing vault.

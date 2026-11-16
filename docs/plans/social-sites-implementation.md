# Social sites Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for assigned tasks.
> Work on your assigned files, run meaningful tests, report interfaces and checks;
> the root agent integrates, reviews, commits and deploys the complete feature.

**Goal:** Operate Telegram, Instagram and Fanvue conversations from one model page.

**Architecture:** One shared database and live tenant worker; web is an authenticated
operator interface, not another messaging agent. Durable commands and existing
pending/action records reconcile web and Telegram bot decisions.

**Tech Stack:** Existing Next.js 16 / React 19, Supabase PostgreSQL, Python worker.

**Spec:** `docs/plans/social-sites-design.md`.

## Global constraints

- Preserve existing Instagram rollout permissions, tenant boundaries and secrets.
- No local worker/Telethon, no live contact test send or seen; root alone deploys.
- Existing verified identities group contacts; candidates never auto-merge.
- Manual is automation Off with explicit operator sends and hard delivery gates.
- UI English, dark app tokens, responsive and keyboard accessible.

## Review focus

- Two operators/web+bot approving the same or replaced draft: exactly one action.
- Switching contacts while polls or typing run: no recipient/text leakage.
- Timeout after provider send or worker lease expiry: uncertain, never blind retry.
- Off/disconnected/no-bot accounts: truthful controls and functional headless drafts.
- Old imported history and wrong identity match: source time and no context leak.

## Task 1 — Data and command contract

Files: new `supabase/migrations/20261116220950_social_sites_inbox.sql`,
`scripts/test-social-sites-db.mjs`.

- [x] Add failing SQL contract tests for isolation, grants, idempotency, grouped
  paging, stale source/identity/suggestions, claim races and uncertain recovery.
- [x] Implement the view/RPC/table interfaces in the spec. Keep all writes service
  only; no API token/secret/prompt in the summary view.
- [x] Run PGlite SQL contracts. Explain any new dependency or interface adjustment.

## Task 2 — Worker operator commands

Files: `worker/src/social_commands.py`, sender/runner/control wiring and focused tests.

- [x] Test duplicate approvals, Manual on all channels, no bot token, source changes,
  quota/flood/window guards, send uncertainty and clean worker cancellation.
- [x] Implement dispatcher with spec RPCs and existing senders, headless proposals,
  explicit operator delivery, bot card synchronization and provider outcomes.
- [x] Run targeted tests and existing affected channel tests. No live execution.

## Task 3 — Authenticated web data and actions

Files: `web/lib/social-types.ts`, `social-server.ts`, `social-policy.ts`,
`web/app/api/models/[id]/social/{route.ts,thread/route.ts}`,
`web/app/app/m/[id]/social/actions.ts`, `web/scripts/social-sites-test.mts`.

- [x] Test hostile/foreign IDs, channel gating, exact proposal/source snapshots,
  validation, timestamp mapping and untrusted provider content.
- [x] Build safe snapshot/thread DTOs and actions, independent authorization per
  request; service-only queue enqueue. No provider sends in Next.js.
- [x] Reads page groups; history loads 50 earlier messages; commands expose actual
  queued vs delivered status. Link/unlink uses audited existing identity functions.

## Task 4 — Social sites interface

Files: `web/components/app/social/*`, `web/app/app/m/[id]/social/page.tsx`,
tab/label registry files. Contracts are `web/lib/social-types.ts`.

- [x] Build channel status/mode cards, person inbox/filter/search/pagination,
  conversation timeline, suggestions/custom composer and linked-person controls.
- [x] Poll safe GET routes every 5s only while visible; preserve local drafts by
  contact, prevent stale request replacement, show all error/empty/offline states.
- [x] Approve exact text or enqueue manual text with one UUID per attempt. Keep
  sender channel explicit, and confirmed linking UI concise and reviewable.
- [x] Check keyboard/mobile/loading states; run typecheck and lint.

## Task 5 — Integrate and ship

- [x] Full worker + SQL contracts, web tests/lint/typecheck/build and independent
  review. Review React best practices after component changes.
- [x] Render real UI with isolated fake data on desktop 1440, mobile 390 and
  dialog 320 px; check overflow, draft isolation, and keyboard-safe dialogs.
  Production browser verification follows deployment.
- [x] Apply reviewed migration, commit/push, deploy web and pinned worker. Verify
  production read-only page/health and update vault with actual shipped behavior.

## Verification before release

- Worker: 2,658 passed, 2 deselected.
- PGlite: Social sites, shared conversations, Fanvue schedule contracts passed.
- Web: policy/server/UI scripts, scoped ESLint, typecheck and production build passed.
- Independent review: mirror resurrection, IG safe retry, late imports and provider
  account changes addressed; no remaining critical/important finding.
- Database migration applied; authenticated has neither queue SELECT nor enqueue EXECUTE.
- No live customer send/seen and no local worker were used during verification.

Live verification also exposed legacy Instagram intent markers in proposals.
The follow-up preview migration renders them for review, freezes canonical text
in the command, and keeps the original suggestion array for CAS. Worker current
offer validation must resolve the same text; a changed URL cannot replace it.

## Production verification

Runtime `39a5309dfe96f2da4652d1c150a4535b53a6e34d` is deployed on Railway
(`78c39dba-b8fd-44d2-bcc3-27a1e4bf6d4f`, SUCCESS) and Vercel production
(`dpl_5QNGGPwjuGh5g68P4QNtaSYQdHYQ`, READY). Both migrations applied.
All three active tenants moved to the new replica and reported fresh heartbeats.
The authenticated production page showed its real grouped inbox, all three linked
channels, channel switching and three marker-free suggestions. No operator command
was submitted during verification. Existing channel modes were preserved.
An existing Instagram provider circuit pause remained visible and was not bypassed.

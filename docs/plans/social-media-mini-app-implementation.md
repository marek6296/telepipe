# Social media and Mini App Implementation Plan

> **For agentic workers:** Use subagent-driven-development for scoped tasks and review.

**Goal:** Play and understand incoming media, and manage Social sites inside Telegram.
**Architecture:** Shared Social workspace, restricted Telegram-authenticated session,
private media archive with persistent analysis and the existing delivery worker.
**Tech Stack:** Next.js/React, Supabase/Postgres/Storage, Python/Telethon, Telegram Mini Apps.
**Spec:** docs/plans/social-media-mini-app-design.md

## Global Constraints
Owner-only media and sessions; no public raw files, secrets, customer sends or seen
on reads. Keep existing mode/schedule/source-version guards. English product UI.

## Review Focus
- Forged Telegram identities and another model's media cannot grant access.
- Re-paired bot invalidates an existing Mini session.
- Video analysis/processing failures remain visible and never invented.
- A new analysis result invalidates old proposals based on placeholders.
- Mobile keyboard, audio/video and navigation preserve unsent drafts.

## Tasks
- [x] Media worker + schema: test media ingest/storage/analysis bounds and retries;
  implement scoped storage and typed metadata for TG/IG/FV, integrate source guards.
- [x] Mini authentication + bot entry: test signed initData/session restrictions;
  implement bootstrap/session endpoints and Social authorization adapter plus menu.
- [x] Compact UI: model selector, mobile workspace, media players with transcript
  and description, reusable command transport, safe areas/back handling.
- [x] Web media backend: owner-authorized message-media DTO and short-lived playback
  URLs with no provider credentials; tests for cross-tenant/channel/media scope.
- [ ] Integrate contracts; full worker/SQL/web checks; independent review and phone
  browser verification; commit/push, deploy, verify real read-only health and vault.

## Validation
- Worker: 2809 passed, 2 deselected; real FFmpeg/ffprobe audio/video fixtures.
- Six PostgreSQL/PGlite suites passed, including semantic revision and reserved-ID races.
- Nine Social/Mini web suites, ESLint, TypeScript and production build passed.
- Independent auth, media, worker and SQL reviews resolved before deployment.
- Mobile fixtures verified at 320/390px, with keyboard, draft isolation, audio playback and URL renewal.
- Owner confirmed the real Telegram Mini App opens chats on mobile without signing in.

## Operational bounds
Private media recovery covers accessible messages from the last seven days. Files
are limited to 40 MiB and audio/video to three minutes. Visual descriptions use
three sampled frames and are labelled accordingly. Failed or expired attachments
remain explicit. No customer test messages or seen receipts are sent.

Production smoke detected a retired Atlas vision default (HTTP 400 not found).
Config now uses the already-supported Gemini model; a real neutral-image request
verified description output and metering. Audio/vision billing records the actual
provider model. Existing successful transcripts are reused on visual-analysis retry.

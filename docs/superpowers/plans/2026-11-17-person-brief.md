# Saved person brief implementation plan

**Goal:** A reusable cross-channel operator summary opened from the chat header.
**Architecture:** Private cache + atomic database generation lease, existing server AI/metering, existing authenticated web/Mini action transports, accessible compact modal.
**Tech stack:** Next.js, React, Supabase Postgres, existing Atlas LLM.
**Spec:** docs/superpowers/specs/2026-11-17-person-brief-design.md

- [x] Add failing policy tests; implement cache identity, bounded chronological context and output validation.
- [x] Add private cache/lease migration and authenticated metered server generation; test cache, failure and membership guards.
- [x] Add shared transport and header modal with saved timestamp, refresh, loading/error and mobile scroll.
- [ ] Run targeted tests, lint, typecheck, build; apply migration and verify grants. Commit, push and verify production. Update project memory.

Review: fixed polling recovery using an interval and allocated a shared input budget across linked accounts. SQL lease/cooldown/privileges verified in PGlite. Actual Don summary used all 235 imported messages across 3 channels; repeated open was cached (one LLM generation). No customer send/read receipt.

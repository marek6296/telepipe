# Shared conversations implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify channel identity, context and day, and deliver scheduled, bounded Instagram interactions without changing Simona's established voice.

**Architecture:** Add tenant-scoped shared services behind the existing channel adapters, durable Instagram actions and transactional PostgreSQL send reservations. Keep the existing Telegram/Fanvue senders, attach shared context and identity guards, and replace Instagram's immediate poll-and-send with ingest/plan/deliver.

**Tech Stack:** Python 3.11, Postgres/Supabase REST RPC, Next.js/React, existing Meta Unified Login.

**Spec:** `docs/superpowers/specs/2026-11-16-instagram-shared-conversation-design.md` plus Marek's execution approval and latest correction: recent invite + name/self-introduction can automatically recognize a likely returning contact, with reversible pairing on denial. Recognition is distinct from access to private history.

## Global Constraints

- All data and queries scoped by model_id and platform ID; handles are mutable hints.
- IG organic window 24 h; no weekly automated DM. No unsupported comment likes.
- Two URL sends per IG account/day LA and rolling 24 h; one promotional URL/contact; Highlights is contextual intent, never canned copy.
- One approved SFW IG photo/contact; no IG voice. Three active IG chats, delayed single actions, strict send-time gates.
- Preserve authored style and no-diacritics; shared LA day and stable tone.
- No unsolicited live test messages; no local worker/Telethon start. Existing authorization covers migrations, commits/push and deployments.
- Reuse current venv/node dependencies without exposing production credentials. Rollout keeps IG Off until operator chooses to enable; no mode changes to existing channels.

## Review Focus

- Lost retries or duplicate sends after timeout/restart: durable states and uncertain outcome reconciliation.
- A false identity match leaks private history: recognition separate from verified merge; denial rolls it back.
- A stale Semi approval bypasses Off/window/takeover: every send goes through current state gates.
- Import marks historical events as fresh: platform timestamp and import watermark, no unsolicited backlog sends.
- A quota race or midnight reset allows extra URL/photo: database transaction plus rolling windows.

### Task 1: Shared policy and database contracts

**Files:** create `worker/src/conversation_policy.py`, `worker/tests/test_conversation_policy.py`, `supabase/migrations/20261116090354_shared_conversations.sql`.
**Interfaces:** policy `parse_time(value)`, `day_key(now,tz)`, `choose_due(kind,now,seed,active=False)`, `classify_input(text)`, `identity_candidate(current,candidates,now)`; database RPCs for atomic action enqueue/claim/reserve/finish and identity reconciliation.
- [ ] Write failing tests: invalid/future timestamps do not open window; same seed preserves delay; nonmatching/ambiguous names never recognized; recent invite + matching self-name recognized; denial detected separately from unrelated negative answers; comments classified before generation.
- [ ] Run `worker/.venv/bin/python -m pytest tests/test_conversation_policy.py -q` from worker (use original workspace venv path in worktree); expected initial failures.
- [ ] Implement pure policies and additive schema with scoped constraints, RLS/revoked client writes, durable actions, shared identities, day state, opt-out and delivery history. RPCs use advisory transaction lock per model; reserve checks both rolling and LA budgets and current conversation revision.
- [ ] Run policy tests; validate migration and concurrency behavior against an isolated PostgreSQL transaction/fixture, including unauthorized grants and quota race contracts.
- [ ] Commit task.

### Task 2: Shared identity, context and day adapters

**Files:** create `worker/src/conversation_hub.py`, `worker/tests/test_conversation_hub.py`; modify `db.py`, `fanvue_tenant.py`, `instagram_tenant.py`, `userbot.py`, `fanvue_agent.py`.
**Interfaces:** `ConversationHub(transport,model_id)`; `observe(platform,external_id,username,name,text)`, `context(platform,external_id)`, `reject_match(...)`, `record_invite(...)`, `day(now,behavior,schedule)`; tenant adapters own `.hub`.
- [ ] Write failing tests for recognition without private history, verified cross-channel context, denial severing only current association, model isolation and identical day across all channels.
- [ ] Implement persistence; shared context reads source channel messages only for verified identities; provisional recognition provides neutral continuity only. Add natural clarification/correction prompt hints and audited manual verification endpoint later in Task 5.
- [ ] Gate old FV tg_id context/payment paths; preserve FV receipts and legacy attribution, don't silently auto-verify legacy heuristics. Append shared context to TG/FV prompt and same saved day state, without replacing their existing style logic.
- [ ] Run relevant TG/FV/day/memory regression tests and new hub tests; commit.

### Task 3: Durable Instagram ingestion and sending

**Files:** create `worker/src/instagram_delivery.py`, `worker/tests/test_instagram_delivery.py`; modify `instagram_agent.py`, `instagram_tenant.py`, `instagram_api.py`, `instagram_start.py`.
**Interfaces:** `InstagramDelivery(db).enqueue(...)`, `.deliver(action,settings,send)`; adapter action RPC methods, timestamp-preserving `add_message`, paginated conversations.
- [ ] Write failing tests: bootstrap imports without sending; current inbound schedules once; restart preserves work; pending reply survives provider failure; approval after expiry/Off/takeover blocked; manual outbound cancels pending work; future/bad dates blocked.
- [ ] Implement ingest watermark/sync mode, page cursors, event types and timestamp storage. Import while Off only when sync enabled. Integrate durable action loop with current sender/control bot and refresh latest remote thread before send.
- [ ] Add schedule gates, per-contact/account budgets and minimum gaps, atomic claim/lease token and uncertain-result state. Reconcile uncertain messages before retry, retain unknown outcomes for review.
- [ ] Run all Instagram tests and relevant control-bot approval tests; commit.

### Task 4: Contextual comments, stories, links and photo

**Files:** modify `instagram_pravidla.py`, `instagram_api.py`, `instagram_agent.py`, `conversation_policy.py`, `instagram_delivery.py`; tests `test_instagram_interactions.py`.
**Interfaces:** structured intent from LLM with allowlisted URL substitution; `react(token,account_id,igsid,mid,emoji)` and `send_photo(...)`; persist selection and due_at by target event.
- [ ] Write failing tests: story question stays DM, emoji queues a reaction, bare story-like is not DM; unsuitable comments skipped; saved selection never rerolls; only one comment action per interval; no private context in public response.
- [ ] Implement typed Meta parsing with documented fixtures, capabilities gates, single photo from approved local photo inventory, no promises when unavailable.
- [ ] Implement server URL allowlist and reservations, Highlights fallback when URL budget exhausted, bounded reminders, one photo/link per identity cluster; ensure style sanitizer preserves allowed URL and strips other URLs.
- [ ] Add stable mood context, repetition protection and optional safe typo policy (never IDs/URLs/numbers/negations; correction map), shared opt-out semantics and age/destination gates.
- [ ] Run interaction plus Instagram regression tests; commit.

### Task 5: Operator controls and observability

**Files:** update `web/lib/instagram.ts`, Instagram settings/page/actions/components; add shared identity review server actions/UI and queue status section; relevant web scripts tests.
**Interfaces:** validated settings for sync, reactions, photos, exact link page, Highlights presence, test scoped ID; owner-scoped identity confirm/reject and Resume.
- [ ] Read local Next docs and write boundary validation tests for URLs, settings and owner-scoped actions.
- [ ] Implement controls with honest capability labels; show scheduled/waiting/expired/uncertain/import status and identity candidates. Human approval does not bypass hard gates.
- [ ] Validate typecheck, ESLint and production build; browser inspect main flows where feasible.
- [ ] Commit.

### Task 6: Integration, review and rollout

**Files:** tests and deployment docs as needed; vault project state/history.
- [ ] Run full worker suite once; record existing unrelated failures distinctly, investigate new regressions. Run web Instagram tests/typecheck/build and `git diff --check`.
- [ ] Fresh whole-branch reviewer per executing-plans skill, including the five Review Focus cases; fix important findings with regressions.
- [ ] Inspect current production schema/status, apply additive migration, verify grants/RPC transactions, merge/push authorized change and deploy pinned Railway SHA + Vercel Git deployment.
- [ ] Verify actual deployment status/logs, read-only import/config health, no unsolicited fan send. Report remaining live Meta capability/test requirements precisely.
- [ ] Update spec implementation status and vault, including exact deployed SHA and limitations.

## Execution rulings

- User explicitly delegated implementation and decisions; proceed natively without another plan/permission round. Independent final review remains required.
- Recognition can be automatic and reversible, but private cross-channel transcript access requires verified linkage. This prevents a plausible Roberto from receiving another Roberto's private messages.
- Unsupported Meta capabilities remain visibly disabled, not simulated using account passwords.

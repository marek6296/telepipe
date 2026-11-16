# Shared conversations implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

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
- [x] Write failing tests: invalid/future timestamps do not open window; same seed preserves delay; nonmatching/ambiguous names never recognized; recent invite + matching self-name recognized; denial detected separately from unrelated negative answers; comments classified before generation.
- [x] Run `worker/.venv/bin/python -m pytest tests/test_conversation_policy.py -q` from worker (use original workspace venv path in worktree); expected initial failures.
- [x] Implement pure policies and additive schema with scoped constraints, RLS/revoked client writes, durable actions, shared identities, day state, opt-out and delivery history. RPCs use advisory transaction lock per model; reserve checks both rolling and LA budgets and current conversation revision.
- [x] Run policy tests; validate migration and concurrency behavior against an isolated PostgreSQL transaction/fixture, including unauthorized grants and quota race contracts.
- [x] Commit task.

### Task 2: Shared identity, context and day adapters

**Files:** create `worker/src/conversation_hub.py`, `worker/tests/test_conversation_hub.py`; modify `db.py`, `fanvue_tenant.py`, `instagram_tenant.py`, `userbot.py`, `fanvue_agent.py`.
**Interfaces:** `ConversationHub(transport,model_id)`; `observe(platform,external_id,username,name,text)`, `context(platform,external_id)`, `reject_match(...)`, `record_invite(...)`, `day(now,behavior,schedule)`; tenant adapters own `.hub`.
- [x] Write failing tests for recognition without private history, verified cross-channel context, denial severing only current association, model isolation and identical day across all channels.
- [x] Implement persistence; shared context reads source channel messages only for verified identities; provisional recognition provides neutral continuity only. Add natural clarification/correction prompt hints and audited manual verification endpoint later in Task 5.
- [x] Gate old FV tg_id context/payment paths; preserve FV receipts and legacy attribution, don't silently auto-verify legacy heuristics. Append shared context to TG/FV prompt and same saved day state, without replacing their existing style logic.
- [x] Run relevant TG/FV/day/memory regression tests and new hub tests; commit.

### Task 3: Durable Instagram ingestion and sending

**Files:** create `worker/src/instagram_delivery.py`, `worker/tests/test_instagram_delivery.py`; modify `instagram_agent.py`, `instagram_tenant.py`, `instagram_api.py`, `instagram_start.py`.
**Interfaces:** `InstagramDelivery(db).enqueue(...)`, `.deliver(action,settings,send)`; adapter action RPC methods, timestamp-preserving `add_message`, paginated conversations.
- [x] Write failing tests: bootstrap imports without sending; current inbound schedules once; restart preserves work; pending reply survives provider failure; approval after expiry/Off/takeover blocked; manual outbound cancels pending work; future/bad dates blocked.
- [x] Implement ingest watermark/sync mode, page cursors, event types and timestamp storage. Import while Off only when sync enabled. Integrate durable action loop with current sender/control bot and refresh latest remote thread before send.
- [x] Add schedule gates, per-contact/account budgets and minimum gaps, atomic claim/lease token and uncertain-result state. Reconcile uncertain messages before retry, retain unknown outcomes for review.
- [x] Run all Instagram tests and relevant control-bot approval tests; commit.

### Task 4: Contextual comments, stories, links and photo

**Files:** modify `instagram_pravidla.py`, `instagram_api.py`, `instagram_agent.py`, `conversation_policy.py`, `instagram_delivery.py`; tests `test_instagram_interactions.py`.
**Interfaces:** structured intent from LLM with allowlisted URL substitution; `react(token,account_id,igsid,mid,emoji)` and `send_photo(...)`; persist selection and due_at by target event.
- [x] Write failing tests: story question stays DM, emoji queues a reaction, bare story-like is not DM; unsuitable comments skipped; saved selection never rerolls; only one comment action per interval; no private context in public response.
- [x] Implement typed Meta parsing with documented fixtures, capabilities gates, single photo from approved local photo inventory, no promises when unavailable.
- [x] Implement server URL allowlist and reservations, Highlights fallback when URL budget exhausted, bounded reminders, one photo/link per identity cluster; ensure style sanitizer preserves allowed URL and strips other URLs.
- [x] Add stable mood context, repetition protection and optional safe typo policy (never IDs/URLs/numbers/negations; correction map), shared opt-out semantics and age/destination gates.
- [x] Run interaction plus Instagram regression tests; commit.

### Task 5: Operator controls and observability

**Files:** update `web/lib/instagram.ts`, Instagram settings/page/actions/components; add shared identity review server actions/UI and queue status section; relevant web scripts tests.
**Interfaces:** validated settings for sync, reactions, photos, exact link page, Highlights presence, test scoped ID; owner-scoped identity confirm/reject and Resume.
- [x] Read local Next docs and write boundary validation tests for URLs, settings and owner-scoped actions.
- [x] Implement controls with honest capability labels; show scheduled/waiting/expired/uncertain/import status and identity candidates. Human approval does not bypass hard gates.
- [x] Validate typecheck, ESLint and production build; browser inspect main flows where feasible.
- [x] Commit.

### Task 6: Integration, review and rollout

**Files:** tests and deployment docs as needed; vault project state/history.
- [x] Run full worker suite once; record existing unrelated failures distinctly, investigate new regressions. Run web Instagram tests/typecheck/build and `git diff --check`.
- [x] Fresh whole-branch reviewer per executing-plans skill, including the five Review Focus cases; fix important findings with regressions.
- [x] Inspect current production schema/status, apply additive migration, verify grants/RPC transactions, merge/push authorized change and deploy pinned Railway SHA + Vercel Git deployment.
- [x] Verify actual deployment status/logs, read-only import/config health, no unsolicited fan send. Report remaining live Meta capability/test requirements precisely.
- [x] Update spec implementation status and vault, including exact deployed SHA and limitations.

## Execution rulings

- User explicitly delegated implementation and decisions; proceed natively without another plan/permission round. Independent final review remains required.
- Recognition can be automatic and reversible, but private cross-channel transcript access requires verified linkage. This prevents a plausible Roberto from receiving another Roberto's private messages.
- Unsupported Meta capabilities remain visibly disabled, not simulated using account passwords.

## Release evidence

Implementation merged/pushed to main; Railway runtime fa7040f SUCCESS, Vercel READY; additive migrations applied. Full worker suite 2413 passed / 2 deselected; SQL tests cover all three migrations, including post-review cross-channel proposal invalidation. Read-only real Meta import is running while IG Off; profile and media/comments reads succeed. Owner IG/TG verified context tested both ways. Live outbound test remains explicitly outside this automated rollout (no fan messages sent). See the spec implementation status for exact limits and review rulings.

## Follow-up: separate invitations and enable Semi

Marek requested Telegram somewhat more often than Linkovne, no repeated recipients, and explicitly enabled Semi. Chosen defaults: TG 4 / LA day and rolling 24 h, gap 2 h; Linkovne 2, gap 4 h; combined 6, gap 1 h. One URL per verified person across destinations remains. Both destinations are contextually selectable with server-owned markers; Semi proposals expose the exact URL, revalidated at send time. Unknown historical/manual URLs consume both budgets. Linkpage invitations are a hint for arrival on TG or FV, never verification. Existing provider pause followed a read failure; measured nested 25-chat read 14.3 s vs 5-chat 7.5 s against 20 s timeout, so cap pages at 5. No outbound send retries introduced.

- [x] RED → GREEN Python interaction/budget/Semi-preview tests and web validator test.
- [x] RED → GREEN actual SQL destination/rolling/gap/recipient/unknown/manual/allowlist contracts.
- [x] Full worker suite 2423 passed, 2 deselected; web typecheck/ESLint/Instagram scripts/build pass.
- [x] Fresh review (Important manual URL classifier + Minor reminder destination fixed with RED→GREEN regressions); migration applied, exact runtime `9984dfc` deployed on Railway SUCCESS and Vercel READY; both + Semi enabled 15:42 UTC. Live read-only Meta conversations request passed (5 chats, 9.9 s); runtime poll 15:42:48 UTC healthy, empty poll_error, no circuit pause and no automated actions. No live fan messages sent.

## Follow-up: unanswered recovery, owner-timed Semi and late read receipts

Marek explicitly requested recovery of unanswered conversations after Off/restart, read receipts shortly before actual replies, and Semi approval at any time across IG/TG/FV. Auto retains the shared LA schedule. Instagram still respects the provider messaging window, current-source/manual-takeover/consent/identity gates and quotas. Existing sent/uncertain/skipped actions must never be resurrected. Only work cancelled by channel pause can be re-enqueued after a fresh read; historical import alone remains read-only. Semi has no timed auto-send fallback.

- [x] TDD IG recent unanswered recovery after Off/restart, idempotent requeue only for channel pause, Semi proposal/send outside schedule; Auto stays scheduled.
- [x] Verify provider read APIs; no read receipts during polling or proposals, only at actual send boundaries. TG/FV independent implementation delegated via dispatching-parallel-agents.
- [x] Remove Semi timed fallback and misleading UI; preserve other send gates.
- [x] Focused tests, DB migration contracts, full suite/web checks, fresh review; apply/deploy exact SHA; read-only production verification and vault update.

Review follow-up: exact 43ad219 review found Skip recovery, mode flips before reserve/during receipt, and stale photo-kind recovery. Fixed with actual UI-status SQL contracts, lease-bound release of an unsent reservation, send-time mode/window checks and fresh action kind. No sent/uncertain action is retried. Read receipt request is bounded to 3 seconds and followed by mode/window revalidation.

TG/FV follow-up: Semi drafts bypass schedule/backlog delays, while Auto checks both the shared behavior window and saved day block at delivery. Fanvue events deferred by the schedule stay unprocessed and durable; owner notifications are claimed once and payment accounting uses an atomic event-bound RPC. Delayed media cannot falsely clear a Telegram pending reply. Independent review additionally found partial Telegram sends missing bookkeeping and reconciled Fanvue purchase thanks losing their retry. Both are fixed and independently verified with six regressions: partial sends finalize only delivered content, and a durable `pending_thanks` flag survives restart even without another webhook. Full worker suite: 2493 passed / 2 deselected. Both disposable SQL suites pass; all three new migrations applied and production service-only RPC grants verified. Web checks passed before the Python-only schedule follow-up. One old source-count test was narrowed to behavior reads for generation, excluding the new read-only schedule check.

Rollout evidence: runtime `c0406697f473da8d5c67360d8705b3b169d798de` pushed to main; Railway `6a775f7c-2ce5-4e0e-9929-eaa9e5c0faa6` SUCCESS and Vercel `dpl_EKv71q9Y5qxwggWaJLoUKB8Q1Z9d` READY. All three runners/heartbeat verified on the new replica. Instagram poll 16:30:29 UTC healthy, no circuit pause; two unanswered threads recovered, first action/pending reply waiting for owner approval, no provider send reservation. Browser confirms Semi, both invitation destinations and new owner-timed explanation. Vault/infra updated. No live fan test message or provider receipt icon test performed.

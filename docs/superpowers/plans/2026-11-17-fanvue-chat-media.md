# Fanvue media implementation plan
Goal: manual free/PPV media bundles in Social web and Mini chats.
Architecture: private worker API job queue for vault/multipart operations, existing durable delivery queue extended with immutable media payload, shared mobile attachment modal.
Spec: docs/superpowers/specs/2026-11-17-fanvue-chat-media-design.md

1. Validate media bundle/price/upload params with failing tests. Add private worker job and send-media queue SQL, test fencing/idempotency/privacy.
2. Implement leased worker media requests and media-aware Fanvue delivery; test ready gating and unknown outcomes.
3. Add authenticated web/Mini transports, multipart uploader and compact Vault/local selection/free-paid modal; test mobile UI and existing send regressions.
4. Apply migration, run worker/web checks, review, commit/push, deploy exact worker and web, verify live vault/readiness without customer sends. Record release in vault.

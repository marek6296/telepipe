# Durable owner waiting queue
User spec: accept approvals/manual replies across chats immediately; worker observes Instagram spacing/quotas in background, closing Mini is safe. Existing seen/pause/source/identity/provider uncertainty rules remain.

1. Regression tests: temporary IG reserve denial yields deferred with exact action ID; dispatcher calls fenced defer RPC rather than terminal finish; manual retries reuse their action. Unknown outcomes never defer.
2. SQL: runtime available_at (excluded from immutable intent), claim skips future work/recent IG reservation but continues other channels; service-only social_defer validates worker/lease/context and exact unreserved operator action, restores only its pending, schedules same command. Allow only known local quota reasons; never provider errors/reserved/uncertain.
3. Worker: typed deferred result, existing action reuse after delay. UI Queued + wait explanation. No provider seen before successful reservation.
4. Disposable real-Postgres checks for defer/due/claim/fencing/immutability; targeted/full worker, web checks and independent review. Apply compatible DB first, deploy worker/web exact SHA, verify live without customer test sends. Record in vault.

# Owner voice implementation plan
Spec: docs/superpowers/specs/2026-11-17-owner-voice-design.md
1. Test spoken preparation/fallback, context ambience and durable preview binding. Add private queue/claim/finish/enqueue SQL with lease and source guards.
2. Implement shared worker preparation/render/storage + TG/FV approved audio delivery and ready gating, preserving Auto behavior.
3. Add web/Mini preview transport + accessible listen/transcript/send dialog and Voice entry points; enable audio Vault/upload.
4. Run targeted, full worker, SQL and web checks; fresh review; deploy compatible backend before frontend. Verify production without customer send. Update vault.

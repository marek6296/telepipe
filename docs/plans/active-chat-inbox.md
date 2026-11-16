# Active chats in the owner bot

The owner needs a durable inbox of reply proposals instead of searching through
Telegram messages. Show three latest conversations at a time, across channels,
with older pages and refresh. Opening a conversation restores its current proposal
card without sending to the contact or marking provider messages read.

Confirmed defect: Instagram proposal keys include an action version, but closing
older cards compared the entire key. A newer action cancelled delivery while the
old owner card stayed awaiting. Group cards by contact when superseding; keep the
version on every send. Check durable action state before listing/opening/approving.

Also protect concurrent owner input: consume a text step before awaiting work,
bind explicit Telegram replies to their prompt, and never route them to another
contact. Restore card context after restarts. Instagram completion must not offer
to approve the same completed action again.

- Regressions: two independent cards, stale versions, latest three plus pagination,
  restart, simultaneous opens/approval, input races and cross-contact replies.
- Implement inbox, conditional card relocation/cleanup, delivery-state validation.
- Run focused and full worker tests; independent review of the final diff.
- Commit/push and pin the worker to the tested commit; verify production state and
  owner menu without sending test messages to contacts.

Implemented: pending UUID inbox links, three-item pages, contact-scoped Instagram
superseding, conditional card relocation, current-action checks, input prompt
bindings with navigation epochs, and draft hashes on numbered buttons. Legacy
buttons refresh before approval. Incomplete Instagram claims are reconciled after
a two-minute grace period only when the durable action proves it was not approved.

Validation: 2,613 worker tests passed, 2 deselected. Independent review findings
were addressed with regressions for source versions, concurrent opens, delayed
input prompts, lost database responses, and legacy approval buttons.

Production verification: runtime `3b15ea0` is pinned on Railway (SUCCESS); all three
tenant runners started on the new replica. Vercel reached READY for the same
commit. Startup retired the orphaned Instagram card. The owner bot returned the
new persistent keyboard and the Active chats page with three waiting conversations
at 21:54 UTC on 2026-11-16. The current Instagram draft remained awaiting, with no
send reservation. No test message or read receipt was sent to a contact.

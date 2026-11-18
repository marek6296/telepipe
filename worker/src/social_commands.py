"""Durable owner commands, executed exclusively by the tenant's existing worker.

No provider credentials, new clients, or delivery retries live here. Each sender
must distinguish definite rejection from an unknown external outcome. Database
RPCs own request idempotency, proposal CAS, worker fencing and claim recovery.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    reason: str = ''
    result: dict = field(default_factory=dict)

    @classmethod
    def sent(cls, provider_id=''):
        return cls('done', result={'provider_message_id': str(provider_id or ''), 'delivery_state': 'sent'})

    @classmethod
    def blocked(cls, reason, *, restore_pending=True):
        return cls('blocked', reason, {'safe_to_retry': True, 'restore_pending': restore_pending})

    @classmethod
    def uncertain(cls, reason='provider_outcome_unknown'):
        return cls('uncertain', reason)


class SocialCommands:
    def __init__(self, transport, model_id, worker_id, control):
        self.transport, self.model_id, self.worker_id = transport, model_id, worker_id
        self.control = control

    async def rpc(self, name, **args):
        return await self.transport._rpc('social_' + name,
            {'p_model': self.model_id, **{'p_' + key: value for key, value in args.items()}})

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                # Never print command bodies or provider responses into logs.
                log.exception('model %s: social command poll failed', self.model_id)
            await asyncio.sleep(1)

    async def regeneration_key(self, command):
        # Instagram's sender requires the exact pending action key (fan:action),
        # whereas Telegram/Fanvue use the contact ID. Resolve only the fenced
        # tenant-owned proposal; never pick a different/newer draft by contact.
        rows = await self.transport._get('/pending_replies', {
            'model_id': 'eq.' + self.model_id, 'id': 'eq.' + command['pending_id'],
            'channel': 'eq.' + command['channel'], 'status': 'eq.awaiting',
            'select': 'conv_key,suggestions', 'limit': '1'})
        if not rows or rows[0]['suggestions'] != command.get('expected_suggestions'):
            return None
        key = str(rows[0].get('conv_key') or '')
        external = command['external_id']
        if key == external or (command['channel'] == 'instagram' and key.split(':', 1)[0] == external and ':' in key):
            return key
        return None

    async def tick(self):
        command = await self.rpc('claim', worker=self.worker_id)
        if not command:
            return
        sender = self.control._senders.get(command['channel'])
        started = False

        async def before_send():
            nonlocal started
            fresh = await self.rpc('start_send', command=command['id'],
                                   lease=command['lease_token'], worker=self.worker_id)
            if fresh:
                started = True
            return bool(fresh)

        try:
            if not sender:
                outcome = DeliveryResult.blocked('channel_unavailable')
            elif command['operation'] == 'regenerate':
                pending = command.get('pending_id')
                if not pending:
                    from owner_drafts import generate
                    output = await generate(sender, command)
                    suggestions = [s for s in (output or {}).get('suggestions', []) if isinstance(s,str) and s.strip()][:3]
                    if not suggestions:
                        outcome = DeliveryResult.blocked('generation_empty')
                    elif await self.rpc('store_owner_draft', worker=self.worker_id, command=command['id'],
                                        lease=command['lease_token'], suggestions=suggestions):
                        await self.control.sync_social_cards()
                        return
                    else:
                        outcome = DeliveryResult('stale','draft_changed')
                else:
                    key = await self.regeneration_key(command)
                    if key is None:
                        await self.rpc('finish', command=command['id'], lease=command['lease_token'],
                                       status='stale', result={}, reason='draft_changed')
                        await self.control.sync_social_cards()
                        return
                    output = await sender.regenerate(key, seed=command['id'], brief=command.get('brief') or '')
                    suggestions = [s for s in (output or {}).get('suggestions', []) if isinstance(s, str) and s.strip()]
                    if not suggestions:
                        outcome = DeliveryResult.blocked('generation_empty')
                    else:
                        changed = await self.rpc('replace_suggestions', pending=pending,
                            expected=command.get('expected_suggestions'), suggestions=suggestions,
                            hint=str((output or {}).get('hint') or ''), command=command['id'],
                            lease=command['lease_token'], worker=self.worker_id)
                        outcome = DeliveryResult('done', result={'regenerated': True}) if changed else DeliveryResult('stale', 'draft_changed')
            else:
                outcome = await sender.deliver_operator(command, before_send)
                if not isinstance(outcome, DeliveryResult):
                    raise TypeError('Sender must return a typed delivery result')
        except asyncio.CancelledError:
            # working expires safely; sending expires to uncertain. Never requeue
            # on shutdown while an external request might already be accepted.
            raise
        except Exception as exc:
            log.warning('model %s: social %s failed (%s)', self.model_id, command['id'], type(exc).__name__)
            outcome = DeliveryResult.uncertain() if started else DeliveryResult('failed', 'preparation_failed', {'safe_to_retry': True})

        if outcome.status == 'deferred_preparation':
            if await self.rpc('defer_preparation', worker=self.worker_id, command=command['id'],
                              lease=command['lease_token'], reason=outcome.reason):
                await self.control.sync_social_cards()
                return
            outcome = DeliveryResult('stale', 'stale_context')

        if outcome.status == 'deferred':
            deferred = await self.rpc('defer', worker=self.worker_id, command=command['id'],
                lease=command['lease_token'], action=outcome.result['action_id'], reason=outcome.reason)
            if deferred:
                await self.control.sync_social_cards()
                return
            outcome = DeliveryResult.blocked('stale_context')

        await self.rpc('finish', command=command['id'], lease=command['lease_token'],
                       status=outcome.status, result=outcome.result, reason=outcome.reason)
        await self.control.sync_social_cards()

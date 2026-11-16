"""Durable, coalesced inbound doorbells. No provider reads or fan sends.

SQL owns message deduplication, batching, mode/account checks and worker lease.
The batch is consumed before Telegram: an ambiguous notification send is never
retried, including after a worker restart.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

log = logging.getLogger(__name__)


def social_url(model_id, channel=None, external_id=None):
    url = f"https://telepipe.me/app/m/{quote(str(model_id), safe='')}/social"
    if channel and external_id is not None:
        url += '?contact=' + quote(f'{channel}:{external_id}', safe='')
    return url


def _line(value, limit):
    text = ' '.join(str(value or '').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def notification_text(item):
    channel = {'telegram': 'Telegram', 'instagram': 'Instagram', 'fanvue': 'Fanvue'}[item['channel']]
    name = _line(item.get('display_name') or item['external_id'], 64)
    count = max(1, int(item.get('message_count') or 1))
    label = 'New message' if count == 1 else f'{count} new messages'
    preview = _line(item.get('preview'), 180) or '[Attachment]'
    return f'{channel} · {name}\n{label}\n{preview}'


class SocialNotifications:
    def __init__(self, transport, model_id, worker_id, control):
        self._t, self.model_id, self.worker_id, self.control = transport, model_id, worker_id, control

    async def tick(self):
        if not self.control.notifications_ready:
            return
        item = await self._t._rpc('social_notification_claim', {
            'p_model': self.model_id, 'p_worker': self.worker_id,
        })
        if not item:
            return
        # SQL may consume/drop a batch when its mode or connection changed.
        if item.get('channel') not in ('telegram', 'instagram', 'fanvue') or not item.get('external_id'):
            log.warning('model %s: invalid inbound notification batch', self.model_id)
            return
        await self.control.notify_inbound(item)

    async def run(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning('model %s: inbound notification failed; consumed batches are not retried',
                            self.model_id, exc_info=True)
            await asyncio.sleep(3)

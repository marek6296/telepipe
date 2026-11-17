"""Owner Vault/multipart metadata requests; bytes go directly browser -> Fanvue.
Uses the tenant's established API/OAuth client. Never sends chat messages here.
"""
from __future__ import annotations
import asyncio
import math
from datetime import datetime, timezone
from urllib.parse import quote, urlparse


def media_rows(body):
    value = body.get('data', body) if isinstance(body, dict) else body
    return list(value.values()) if isinstance(value, dict) else value if isinstance(value, list) else []


def media_item(row):
    variants = row.get('variants') or []
    thumb = next((v.get('url') for v in variants if v.get('variantType') in ('thumbnail', 'thumbnailBlurred')), '')
    if not thumb and str(row.get('mediaType') or row.get('type') or '').lower() == 'image':
        thumb = next((v.get('url') for v in variants if v.get('variantType') == 'main'), '')
    if not isinstance(thumb, str) or urlparse(thumb).scheme != 'https':
        thumb = ''
    return {'uuid': str(row.get('uuid') or ''), 'name': str(row.get('name') or row.get('filename') or '')[:200],
            'kind': str(row.get('mediaType') or row.get('type') or '').lower(),
            'status': str(row.get('status') or ''), 'thumb': thumb}


async def call(api, method, path, **kwargs):
    response = await api._client.request(method, path, headers=await api._headers(), **kwargs)
    response.raise_for_status()
    return response.json()


async def ready_media(api, ids, db=None):
    if not ids or len(ids) > 20 or len(set(ids)) != len(ids):
        return False
    body = await call(api, 'GET', '/media/bulk', params={'mediaUuids': ','.join(ids), 'variants': 'thumbnail,main'})
    rows = {str(r.get('uuid')): r for r in media_rows(body)}
    valid = all(i in rows and rows[i].get('status') == 'ready'
               and str(rows[i].get('mediaType') or rows[i].get('type') or '').lower() in ('image', 'video') for i in ids)
    if valid and db is not None:
        # Uploaded items may not have reached the background Vault sync yet.
        # Seed only provider fields so send receipts have a parent; preserve
        # the owner's caption, price, folder and AI-selection settings.
        await db.upsert_media([{'media_uuid': i, 'kind': media_item(rows[i])['kind'],
                                'thumb_url': media_item(rows[i])['thumb']} for i in ids])
    return valid


class FanvueOwnerMedia:
    def __init__(self, transport, model_id, worker_id, control):
        self.t, self.model, self.worker, self.control = transport, model_id, worker_id, control

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                # Metadata may contain presigned URLs: never log exception bodies.
                pass
            await asyncio.sleep(1)

    async def tick(self):
        job = await self.t._rpc('social_claim_fanvue_request', {'p_model': self.model, 'p_worker': self.worker})
        if not job:
            return
        result, error = {}, ''
        try:
            sender = self.control._senders.get('fanvue')
            if not sender:
                raise ValueError('Fanvue is not connected.')
            config = await sender._db.settings()
            if not config.get('connected') or job['account_scope'] != 'fanvue:' + str(config.get('creator_uuid') or ''):
                raise ValueError('The Fanvue account changed. Reopen the media picker.')
            result = await self.handle(sender, job)
        except ValueError as exc:
            error = str(exc)
        except Exception:
            error = 'Fanvue could not finish this media request. Try again. No message was sent.'
        await self.t._rpc('social_finish_fanvue_request', {'p_model': self.model, 'p_worker': self.worker,
            'p_id': job['id'], 'p_lease': job['lease_token'], 'p_output': result, 'p_error': error})

    async def upload_session(self, job):
        rows = await self.t._get('/social_fanvue_requests', {'model_id': 'eq.' + self.model,
            'id': 'eq.' + job['input']['uploadKey'], 'account_scope': 'eq.' + job['account_scope'],
            'action': 'eq.init', 'status': 'eq.done', 'expires_at': 'gt.' + datetime.now(timezone.utc).isoformat(), 'select': 'output'})
        if not rows:
            raise ValueError('Upload session expired. Select the file again.')
        return rows[0]['output']

    async def handle(self, sender, job):
        api, data, action = sender._api, job['input'], job['action']
        if action == 'list':
            params = {'page': data.get('page', 1), 'size': 50, 'status': 'ready', 'variants': 'thumbnail,main'}
            if data.get('folder'):
                params['folderName'] = data['folder']
            body = await call(api, 'GET', '/media', params=params)
            items = [media_item(row) for row in media_rows(body)]
            folders = await sender._db.folders()
            return {'items': [item for item in items if item['kind'] in ('image', 'video')],
                    'hasMore': (body.get('pagination') or {}).get('hasMore', len(items) == 50),
                    'folders': [f['name'] for f in folders]}
        if action == 'init':
            file = data['file']
            if file['mediaType'] not in ('image', 'video') or not 0 < file['size'] <= 1610612736:
                raise ValueError('Unsupported file type or size.')
            body = await call(api, 'POST', '/media/uploads', json={'name': file['name'], 'filename': file['name'],
                'mediaType': file['mediaType'], 'sizeBytes': file['size']})
            part_size = int(body['partSize'])
            total = math.ceil(file['size'] / part_size)
            if not 1 <= total <= int(body.get('maxParts') or 256):
                raise ValueError('Fanvue rejected the file size.')
            return {'mediaUuid': body['mediaUuid'], 'uploadId': body['uploadId'], 'partSize': part_size,
                    'totalParts': total, 'name': file['name'], 'kind': file['mediaType']}
        session = await self.upload_session(job)
        upload = quote(session['uploadId'], safe='')
        if action == 'part':
            start, end = int(data['from']), int(data['to'])
            if not 1 <= start <= end <= session['totalParts'] or end - start >= 8:
                raise ValueError('Invalid upload part range.')
            body = await call(api, 'GET', f'/media/uploads/{upload}/parts/urls', params={'from': start, 'to': end})
            parts = body.get('parts') or []
            if len(parts) != end - start + 1 or any(urlparse(p['url']).scheme != 'https' for p in parts):
                raise ValueError('Fanvue did not return usable upload URLs.')
            return {'parts': parts}
        if action == 'complete':
            parts = data['parts']
            if sorted(p['PartNumber'] for p in parts) != list(range(1, session['totalParts'] + 1)):
                raise ValueError('Upload is missing parts. Select the file again.')
            await call(api, 'PATCH', f'/media/uploads/{upload}', json={'parts': parts})
            return {'mediaUuid': session['mediaUuid'], 'status': 'processing'}
        if action == 'status':
            body = await call(api, 'GET', '/media/' + session['mediaUuid'], params={'variants': 'thumbnail,main'})
            body = body.get('data', body)
            return {'item': media_item(body)}
        raise ValueError('Unsupported media action.')

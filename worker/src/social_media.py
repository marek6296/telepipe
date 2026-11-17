"""Private inbound attachments and the exact analysis shared by owner and agent.

Provider URLs live only in this process. Claims precede downloads and paid calls;
the database joins provider IDs to tenant-owned history and fences finalization.
No function in this module sends a message or marks a conversation as read.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)
MAX_BYTES = 40 * 1024 * 1024
MAX_SECONDS = 180
MAX_ATTACHMENTS = 6
BUCKET = 'social-media'
_slots = asyncio.Semaphore(2)


class MediaError(Exception):
    def __init__(self, code, unavailable=False):
        super().__init__(code)
        self.code, self.unavailable = code, unavailable


def validate_url(url, channel):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        suffixes = {'instagram': ('cdninstagram.com', 'fbcdn.net', 'fbsbx.com', 'facebook.com'),
                    'fanvue': ('fanvue.com', 'fanvue.net', 'fanvuecdn.com')}[channel]
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not any(host == suffix or host.endswith('.' + suffix) for suffix in suffixes)):
            raise ValueError()
    except (ValueError, KeyError):
        raise MediaError('unsafe_source', True) from None
    return host


async def download(url, channel):
    host = validate_url(url, channel)
    addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
        raise MediaError('unsafe_source', True)
    # A separate client deliberately has no provider/service authorization or
    # cookies. Redirects are rejected, including redirects into private networks.
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        async with client.stream('GET', url, headers={'Accept-Encoding': 'identity'}) as response:
            if response.status_code in (401, 403, 404, 410):
                raise MediaError('source_unavailable', True)
            if response.is_redirect:
                raise MediaError('unsafe_redirect', True)
            response.raise_for_status()
            if int(response.headers.get('content-length') or 0) > MAX_BYTES:
                raise MediaError('file_too_large', True)
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise MediaError('file_too_large', True)
            return bytes(data)


def instagram_attachments(items):
    result = []
    for index, item in enumerate(items[:MAX_ATTACHMENTS]):
        mime = str(item.get('mime_type') or '')
        kind = str(item.get('type') or mime.split('/')[0]).lower()
        url = (item.get('payload') or {}).get('url') or item.get('file_url') or ''
        for field, candidate in (('video_data', 'video'), ('audio_data', 'audio'), ('image_data', 'image')):
            if item.get(field):
                kind = candidate
                blob = item[field]
                url = (blob.get('url') or blob.get('src') or '') if isinstance(blob, dict) else str(blob)
                break
        result.append({'key': str(item.get('id') or index), 'kind': kind if kind in ('audio', 'video', 'image') else 'file',
                       'mime': mime, 'url': url})
    return result


def telegram_attachment(message):
    doc = getattr(message, 'document', None)
    photo = getattr(message, 'photo', None)
    mime = str(getattr(doc, 'mime_type', '') or '')
    if getattr(message, 'voice', None) or getattr(message, 'audio', None) or mime.startswith('audio/'):
        kind = 'audio'
    elif getattr(message, 'video', None) or getattr(message, 'video_note', None) or mime.startswith('video/'):
        kind = 'video'
    elif photo or mime.startswith('image/'):
        kind = 'image'
    elif doc:
        kind = 'file'
    else:
        return None
    return {'key': str(getattr(doc or photo, 'id', None) or '0'), 'kind': kind, 'mime': mime,
            'size': int(getattr(doc, 'size', 0) or 0)}


def fanvue_attachments(message, api, external):
    """Resolve stable chat media IDs only after winning the durable claim."""
    ids = message.get('mediaUuids') or message.get('media_uuids') or []
    kind = str(message.get('mediaType') or '').lower()
    kind = kind if kind in ('image', 'video', 'audio') else 'file'
    parts = []
    for media_id in ids[:MAX_ATTACHMENTS]:
        async def loader(key=str(media_id)):
            try:
                rows = await api.chat_media(external, message['uuid'], [key])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (403, 404, 410):
                    raise MediaError('source_unavailable', True) from None
                raise
            item = next((r for r in rows if str(r.get('uuid')) == key), None)
            if not item:
                raise MediaError('source_unavailable', True)
            if item.get('status') in ('created', 'processing'):
                raise MediaError('provider_processing')
            variant = next((v for v in item.get('variants', []) if v.get('variantType') == 'main' and v.get('url')), None)
            if not variant:
                raise MediaError('source_unavailable', True)
            return await download(variant['url'], 'fanvue')
        parts.append({'key': str(media_id), 'kind': kind, 'loader': loader})
    # Provider can report a hidden/expired attachment without returning IDs.
    return parts or [{'key': 'unavailable', 'kind': kind, 'url': ''}]


async def telegram_bytes(client, message):
    data = bytearray()
    async with asyncio.timeout(40):
        async for chunk in client.iter_download(message.media):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise MediaError('file_too_large', True)
    return bytes(data)


async def _run(*args, timeout=45):
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise MediaError('invalid_media', True)
    return output


class SocialMedia:
    def __init__(self, transport, model_id, llm):
        self.t, self.model, self.llm = transport, model_id, llm

    async def upload(self, path, data, mime):
        base = str(self.t._client.base_url).split('/rest/v1')[0]
        response = await self.t._client.post(f'{base}/storage/v1/object/{BUCKET}/{path}', content=data,
            headers={'Content-Type': mime, 'x-upsert': 'true'}, timeout=40)
        response.raise_for_status()

    async def context(self, channel, external, scope, provider_id):
        """Return the same durable text used by generation and the owner UI."""
        rows = await self.t._get('/social_message_media', {'model_id': f'eq.{self.model}',
            'channel': f'eq.{channel}', 'external_id': f'eq.{external}', 'account_scope': f'eq.{scope}',
            'provider_message_id': f'eq.{provider_id}', 'select': 'message_id,transcript,description,status',
            'limit': str(MAX_ATTACHMENTS)})
        if not rows or not any(row.get('transcript') or row.get('description') for row in rows):
            return None
        table = {'telegram': '/dm_messages', 'instagram': '/ig_messages', 'fanvue': '/fv_messages'}[channel]
        messages = await self.t._get(table, {'model_id': f'eq.{self.model}', 'id': f"eq.{rows[0]['message_id']}",
            'select': 'content', 'limit': '1'})
        return messages[0]['content'] if messages else None

    async def prepare(self, data, kind):
        if not data or len(data) > MAX_BYTES:
            raise MediaError('file_too_large' if data else 'empty_media', True)
        if kind == 'file':
            raise MediaError('unsupported_media', True)
        formats = 'mov,matroska,webm,ogg,mp3,wav,aac,flac,jpeg_pipe,png_pipe,gif'
        with tempfile.TemporaryDirectory(prefix='telepipe-media-') as directory:
            root = Path(directory)
            source = root / 'input'
            source.write_bytes(data)
            probe = json.loads(await _run('ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                '-format_whitelist', formats, '-show_format', '-show_streams', '-of', 'json', str(source), timeout=15))
            try:
                duration = float((probe.get('format') or {}).get('duration') or 0)
            except (TypeError, ValueError):
                raise MediaError('duration_limit', True) from None
            # Never present a silently truncated prefix as the whole message.
            if not math.isfinite(duration) or duration < 0 or duration > MAX_SECONDS or (kind != 'image' and duration == 0):
                raise MediaError('duration_limit', True)
            streams = probe.get('streams') or []
            if len(streams) > 16 or any(
                max(int(s.get('width') or 0), int(s.get('height') or 0)) > 8192
                or int(s.get('width') or 0) * int(s.get('height') or 0) > 30_000_000 for s in streams):
                raise MediaError('dimensions_limit', True)
            has_audio = any(s.get('codec_type') == 'audio' for s in streams)
            has_video = any(s.get('codec_type') == 'video' for s in streams)
            if (kind == 'audio' and not has_audio) or (kind in ('video', 'image') and not has_video):
                raise MediaError('invalid_media', True)
            base = ('ffmpeg', '-v', 'error', '-nostdin', '-y', '-threads', '1', '-protocol_whitelist', 'file,pipe',
                    '-format_whitelist', formats, '-i', str(source))
            audio = None
            if has_audio:
                audio_file = root / 'audio.mp3'
                await _run(*base, '-map', '0:a:0', '-vn', '-t', str(MAX_SECONDS), '-ac', '1', '-ar', '16000', '-b:a', '48k', str(audio_file))
                audio = audio_file.read_bytes()
            frames = []
            if kind in ('image', 'video'):
                times = [0] if kind == 'image' else sorted(set([0, round(duration / 2, 2), max(0, round(duration - .5, 2))]))
                for index, second in enumerate(times):
                    frame = root / f'frame{index}.jpg'
                    await _run(*base, '-ss', str(second), '-frames:v', '1', '-vf', 'scale=640:640:force_original_aspect_ratio=decrease', '-threads', '1', str(frame))
                    if frame.exists():
                        frames.append((second, frame.read_bytes()))
            if kind in ('image', 'video') and not frames:
                raise MediaError('invalid_media', True)
            if kind == 'audio':
                playback, mime, ext = audio, 'audio/mpeg', 'mp3'
            elif kind == 'image':
                playback, mime, ext = frames[0][1], 'image/jpeg', 'jpg'
            else:
                output = root / 'video.mp4'
                await _run(*base, '-map', '0:v:0', '-map', '0:a:0?', '-t', str(MAX_SECONDS),
                    '-vf', 'scale=720:720:force_original_aspect_ratio=decrease:force_divisible_by=2', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '27',
                    '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart',
                    '-fs', str(MAX_BYTES), str(output), timeout=60)
                if output.stat().st_size >= MAX_BYTES:
                    raise MediaError('file_too_large', True)
                converted = json.loads(await _run('ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(output), timeout=15))
                converted_duration = float((converted.get('format') or {}).get('duration') or 0)
                if converted_duration < duration - .25:
                    raise MediaError('incomplete_media', True)
                playback, mime, ext = output.read_bytes(), 'video/mp4', 'mp4'
            return {'playback': playback, 'mime': mime, 'ext': ext, 'audio': audio,
                    'frames': frames, 'duration': duration or None}

    async def ingest(self, channel, external, scope, provider_id, attachments, *, occurred_at=None, role=None):
        """Runs inline before generation, including Manual/read-only polling.

        SQL returns no claim for completed/busy/backoff items. Up to six parts
        are processed per message; each claim allows at most three attempts.
        """
        async with _slots:
            processed = 0
            for part in attachments[:MAX_ATTACHMENTS]:
                claim = await self.t._rpc('social_media_claim', {'p_model': self.model, 'p_channel': channel,
                    'p_external': str(external), 'p_scope': scope, 'p_provider_id': str(provider_id),
                    'p_attachment': part['key'], 'p_kind': part['kind'],
                    'p_occurred_at': occurred_at, 'p_role': role})
                if not claim:
                    continue
                processed += 1
                result = {}
                try:
                    async with asyncio.timeout(240):
                        if int(part.get('size') or 0) > MAX_BYTES:
                            raise MediaError('file_too_large', True)
                        if part.get('loader'):
                            data = await part['loader']()
                        elif part.get('url'):
                            data = await download(part['url'], channel)
                        else:
                            raise MediaError('source_unavailable', True)
                        prepared = await self.prepare(data, part['kind'])
                        path = f"{self.model}/{channel}/{claim['message_id']}/{claim['id']}.{prepared['ext']}"
                        await self.upload(path, prepared['playback'], prepared['mime'])
                        result.update(storage_path=path, mime_type=prepared['mime'], duration_seconds=prepared['duration'])
                        if claim.get('transcript'):
                            result['transcript'] = claim['transcript']
                        elif prepared['audio']:
                            transcript = await self.llm.transcribe_voice(prepared['audio'], fmt='mp3')
                            if transcript:
                                result['transcript'] = transcript
                            else:
                                result['error'] = 'transcription_unavailable'
                        descriptions = [claim['description']] if claim.get('description') else []
                        for second, frame in ([] if descriptions else prepared['frames']):
                            seen = await self.llm.describe_image(frame, mime='image/jpeg')
                            if seen.get('description'):
                                description = seen['description']
                                if seen.get('explicit'):
                                    description = f"[poslal EXPLICITNÚ fotku: {description}]"
                                elif seen.get('kind') == 'SCREENSHOT':
                                    description = f"[poslal SNÍMKU OBRAZOVKY: {description}]"
                                descriptions.append(f"{second:g}s: {description}" if part['kind'] == 'video' else description)
                        if descriptions:
                            result['description'] = '\n'.join(descriptions)
                        elif part['kind'] in ('video', 'image'):
                            result['error'] = 'description_unavailable'
                        result['status'] = 'failed' if result.get('error') else 'ready'
                except MediaError as exc:
                    result.update(status='unavailable' if exc.unavailable else 'failed', error=exc.code)
                except Exception:
                    # Provider exceptions may contain signed URLs or headers.
                    log.warning('Media processing failed (%s, %s)', channel, claim['id'])
                    result.update(status='failed', error='processing_failed')
                await self.t._rpc('social_media_finish', {'p_model': self.model, 'p_id': claim['id'],
                    'p_lease': claim['lease_token'], 'p_result': result})
            return processed


def for_db(db, llm):
    """Standalone legacy adapters have no tenant transport; production does."""
    transport, model = getattr(db, '_t', None), getattr(db, 'model_id', None)
    return SocialMedia(transport, model, llm) if transport and model else None

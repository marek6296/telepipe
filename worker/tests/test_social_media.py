"""Private incoming media: provider bytes, truthful analysis and safe retries."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import httpx
import social_media

from social_media import MediaError, SocialMedia, instagram_attachments, telegram_attachment, validate_url


def test_instagram_audio_video_and_unavailable_attachments():
    rows = instagram_attachments([
        {'id': 'a', 'mime_type': 'audio/mp4', 'file_url': 'https://lookaside.fbsbx.com/a'},
        {'id': 'v', 'video_data': {'url': 'https://scontent.cdninstagram.com/v'}},
        {'id': 'gone', 'type': 'ephemeral'},
    ])
    assert [r['kind'] for r in rows] == ['audio', 'video', 'file']
    assert rows[2]['url'] == ''


@pytest.mark.parametrize('url', ['http://cdn.fanvue.com/a', 'https://127.0.0.1/a',
    'https://fanvue.com.evil.test/a', 'https://user:secret@cdn.fanvue.com/a',
    'https://cdn.fanvue.com:444/a', 'file:///tmp/a'])
def test_download_rejects_untrusted_targets(url):
    with pytest.raises(MediaError):
        validate_url(url, 'fanvue')


def test_telegram_round_video_is_video_and_voice_is_audio():
    assert telegram_attachment(SimpleNamespace(video_note=True, document=SimpleNamespace(size=12, mime_type='video/mp4', id=7)))['kind'] == 'video'
    assert telegram_attachment(SimpleNamespace(voice=True, document=SimpleNamespace(size=12, mime_type='audio/ogg', id=8)))['kind'] == 'audio'


class Transport:
    def __init__(self):
        self.calls = []
        self.claim = {'id': 'media-id', 'message_id': 3, 'lease_token': 'lease', 'storage_path': None}
    async def _rpc(self, name, args):
        self.calls.append((name, args))
        return self.claim if name == 'social_media_claim' else True


@pytest.mark.asyncio
async def test_store_before_analysis_and_same_transcript_is_finalized():
    t, llm = Transport(), SimpleNamespace(transcribe_voice=AsyncMock(return_value='hello from audio'))
    svc = SocialMedia(t, 'model', llm)
    svc.upload = AsyncMock()
    svc.prepare = AsyncMock(return_value={'playback': b'mp3', 'mime': 'audio/mpeg', 'ext': 'mp3', 'audio': b'mp3', 'frames': [], 'duration': 3})
    loader = AsyncMock(return_value=b'original')
    await svc.ingest('telegram', 'fan', 'account', 'provider-id', [{'key': 'one', 'kind': 'audio', 'loader': loader}])
    assert svc.upload.await_count == 1
    final = t.calls[-1][1]['p_result']
    assert final['transcript'] == 'hello from audio'
    assert final['status'] == 'ready'
    assert final['storage_path'] == 'model/telegram/3/media-id.mp3'
    assert not any('url' in key for key in final)


@pytest.mark.asyncio
async def test_claim_deduplicates_before_download_or_billing():
    t = Transport(); t.claim = None
    svc = SocialMedia(t, 'model', SimpleNamespace())
    loader = AsyncMock()
    await svc.ingest('telegram', 'fan', 'account', 'provider-id', [{'key': 'one', 'kind': 'audio', 'loader': loader}])
    loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_analysis_failure_preserves_private_playback_without_fake_transcript():
    t = Transport()
    svc = SocialMedia(t, 'model', SimpleNamespace(transcribe_voice=AsyncMock(return_value='')))
    svc.upload = AsyncMock()
    svc.prepare = AsyncMock(return_value={'playback': b'audio', 'mime': 'audio/mpeg', 'ext': 'mp3', 'audio': b'audio', 'frames': [], 'duration': 1})
    await svc.ingest('telegram', 'fan', 'scope', 'mid', [{'key': 'one', 'kind': 'audio', 'loader': AsyncMock(return_value=b'audio')}])
    final = t.calls[-1][1]['p_result']
    assert final['status'] == 'failed'
    assert final['error'] == 'transcription_unavailable'
    assert final['storage_path']
    assert not final.get('transcript')


@pytest.mark.asyncio
async def test_video_gets_visual_description_and_spoken_transcript():
    t = Transport()
    llm = SimpleNamespace(transcribe_voice=AsyncMock(return_value='spoken words'), describe_image=AsyncMock(return_value={'description': 'A person waves.'}))
    svc = SocialMedia(t, 'model', llm)
    svc.upload = AsyncMock()
    svc.prepare = AsyncMock(return_value={'playback': b'video', 'mime': 'video/mp4', 'ext': 'mp4', 'audio': b'audio', 'frames': [(0.0, b'jpeg')], 'duration': 3})
    await svc.ingest('instagram', 'fan', 'scope', 'mid', [{'key': 'one', 'kind': 'video', 'loader': AsyncMock(return_value=b'video')}])
    final = t.calls[-1][1]['p_result']
    assert final['status'] == 'ready'
    assert final['transcript'] == 'spoken words'
    assert 'A person waves.' in final['description']


@pytest.mark.asyncio
async def test_expired_provider_source_is_explicitly_unavailable():
    t = Transport(); svc = SocialMedia(t, 'model', SimpleNamespace())
    await svc.ingest('instagram', 'fan', 'scope', 'mid', [{'key': 'gone', 'kind': 'video', 'url': ''}])
    final = t.calls[-1][1]['p_result']
    assert final == {'status': 'unavailable', 'error': 'source_unavailable'}


@pytest.mark.asyncio
async def test_fanvue_resolves_scoped_chat_media_only_after_claim(monkeypatch):
    api = SimpleNamespace(chat_media=AsyncMock(return_value=[{'uuid': 'attachment', 'status': 'ready',
        'variants': [{'variantType': 'blurred', 'url': 'https://cdn.fanvue.com/blurred'},
                     {'variantType': 'main', 'url': 'https://cdn.fanvue.com/private'}]}]))
    fetch = AsyncMock(return_value=b'private bytes')
    monkeypatch.setattr(social_media, 'download', fetch)
    parts = social_media.fanvue_attachments({'uuid': 'message', 'hasMedia': True, 'mediaType': 'audio',
        'mediaUuids': ['attachment']}, api, 'fan')
    api.chat_media.assert_not_awaited()
    assert await parts[0]['loader']() == b'private bytes'
    api.chat_media.assert_awaited_once_with('fan', 'message', ['attachment'])
    fetch.assert_awaited_once_with('https://cdn.fanvue.com/private', 'fanvue')


@pytest.mark.asyncio
async def test_fanvue_does_not_substitute_a_locked_blurred_preview():
    api = SimpleNamespace(chat_media=AsyncMock(return_value=[{'uuid': 'attachment', 'status': 'ready',
        'variants': [{'variantType': 'blurred', 'url': 'https://cdn.fanvue.com/blurred'}]}]))
    part = social_media.fanvue_attachments({'uuid': 'message', 'hasMedia': True, 'mediaType': 'video',
        'mediaUuids': ['attachment']}, api, 'fan')[0]
    with pytest.raises(MediaError, match='source_unavailable'):
        await part['loader']()


@pytest.mark.asyncio
async def test_bounded_telegram_download_never_marks_seen(monkeypatch):
    monkeypatch.setattr(social_media, 'MAX_BYTES', 4)
    class Client:
        def iter_download(self, media):
            async def chunks():
                yield b'123'; yield b'456'
            return chunks()
    with pytest.raises(MediaError, match='file_too_large'):
        await social_media.telegram_bytes(Client(), SimpleNamespace(media='document'))


@pytest.mark.asyncio
async def test_retry_reuses_successful_transcription_and_description():
    t = Transport(); t.claim.update(transcript='already paid', description='already seen')
    llm = SimpleNamespace(transcribe_voice=AsyncMock(), describe_image=AsyncMock())
    svc = SocialMedia(t, 'model', llm)
    svc.upload = AsyncMock()
    svc.prepare = AsyncMock(return_value={'playback': b'video', 'mime': 'video/mp4', 'ext': 'mp4', 'audio': b'audio', 'frames': [(0, b'jpeg')], 'duration': 1})
    await svc.ingest('telegram', 'fan', 'scope', 'mid', [{'key': 'one', 'kind': 'video', 'loader': AsyncMock(return_value=b'video')}])
    llm.transcribe_voice.assert_not_awaited()
    llm.describe_image.assert_not_awaited()
    assert t.calls[-1][1]['p_result']['status'] == 'ready'


@pytest.mark.asyncio
async def test_instagram_source_revision_uses_semantic_summary():
    from instagram_tenant import TenantInstagramDb
    t = SimpleNamespace(_get=AsyncMock(return_value=[{'last_message_id': '501'}]))
    db = TenantInstagramDb(t, 'model', '')
    assert await db.latest_message_id('fan') == 501
    assert t._get.call_args.args[0] == '/social_contact_summaries'


@pytest.mark.asyncio
async def test_billing_uses_existing_audio_and_vision_ledger_kinds():
    from credits import MeteredLlm
    raw = SimpleNamespace(last_usage={'input': 12, 'output': 8}, last_model='configured-model',
        transcribe_voice=AsyncMock(return_value='spoken'), describe_image=AsyncMock(return_value={'description': 'view'}))
    reg = SimpleNamespace(credit_state=AsyncMock(return_value=(100, False)),
        pricing=AsyncMock(return_value={'input_usd_per_mtok': 1, 'output_usd_per_mtok': 2}),
        record_usage=AsyncMock())
    llm = MeteredLlm(raw, reg, 'model', 'fallback')
    await llm.transcribe_voice(b'audio', fmt='mp3'); await llm.describe_image(b'jpeg')
    assert [c.args[1] for c in reg.record_usage.call_args_list] == ['audio', 'vision']


@pytest.mark.asyncio
async def test_telegram_persists_before_media_claim_without_seen_or_send():
    from test_telegram_native_sync import setup, STAMP
    bot, db, client = setup()
    async def ingest(*args, **kwargs):
        assert db.ingested[-1]['key'][-1] == 120
        assert args[:4] == ('telegram', '555', 'telegram:account-one', '120')
        assert args[4][0]['kind'] == 'audio'
        return 1
    bot._incoming_media = SimpleNamespace(ingest=AsyncMock(side_effect=ingest))
    source = SimpleNamespace(id=120, date=STAMP, out=False, voice=True,
        document=SimpleNamespace(id=10, size=32, mime_type='audio/ogg'))
    await bot._record_telegram(555, source, 'user', '[voice]')
    bot._incoming_media.ingest.assert_awaited_once()
    assert not client.sent


@pytest.mark.asyncio
async def test_fanvue_manual_sync_processes_known_incoming_media_without_send():
    from test_fanvue_native_sync import setup
    agent, db, api, cards = setup()
    db.config.update(reply_mode='off', enabled=False)
    api.messages[0].update(hasMedia=True, mediaType='audio', mediaUuids=['audio-uuid'])
    agent._incoming_media = SimpleNamespace(ingest=AsyncMock(return_value=1))
    await agent._reconcile({'uuid': 'fan', 'text': ''}, dict(db.user), sync_only=True)
    args = agent._incoming_media.ingest.call_args.args
    assert args[:4] == ('fanvue', 'fan', 'fanvue:creator', 'incoming')
    assert args[4][0]['kind'] == 'audio'
    assert not api.seen and not api.sent and not cards


@pytest.mark.asyncio
async def test_instagram_manual_ingest_processes_known_attachment_without_seen(monkeypatch):
    from datetime import datetime, timezone
    from test_instagram_delivery import thread, settings
    from instagram_delivery import InstagramDelivery
    db = AsyncMock(model_id='model')
    db.ensure_user.return_value = {}
    db.hub.restrictions.return_value = {}
    db.known_mids.return_value = {'incoming'}
    db.processed_mids.return_value = {'incoming'}
    db.actions.return_value = []
    delivery = InstagramDelivery(db, AsyncMock())
    delivery.media = SimpleNamespace(ingest=AsyncMock(return_value=1), context=AsyncMock(return_value='Transcript: actual words'))
    raw = thread(datetime.now(timezone.utc))
    raw['messages']['data'][0]['attachments'] = {'data': [{'id': 'a', 'mime_type': 'audio/mp4', 'file_url': 'https://lookaside.fbsbx.com/a'}]}
    cfg = settings(); cfg.update(reply_mode='off', enabled=False)
    await delivery.ingest(raw, cfg, bootstrap=True)
    args = delivery.media.ingest.call_args.args
    assert args[:4] == ('instagram', 'fan', 'account', 'incoming')
    assert args[4][0]['kind'] == 'audio'
    db.add_message.assert_not_awaited()
    db.rpc.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_voice_transcript_is_not_cut_to_six_hundred_characters():
    from llm import Llm
    content = 'This is the full spoken transcript. ' * 50
    llm = Llm('test-key', 'configured')
    await llm._client.aclose()
    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200,
        json={'choices': [{'message': {'content': content}}], 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}})))
    try:
        assert await llm.transcribe_voice(b'fake fixture', fmt='mp3') == content.strip()
    finally:
        await llm.close()


@pytest.mark.asyncio
async def test_telegram_own_bubbles_advance_to_row_revision_not_primary_key():
    from test_telegram_native_sync import setup, message
    bot, db, client = setup()
    bot._generation_sources[555] = 40
    client.send_message = AsyncMock(side_effect=[message(123, 'first'), message(124, 'second')])
    bot._record_telegram = AsyncMock(side_effect=[{'id': 10, 'source_version': 41}, {'id': 12, 'source_version': 43}])
    await bot._send_tracked(555, 'first')
    assert bot._generation_sources[555] == 41
    await bot._send_tracked(555, 'second')
    assert bot._generation_sources[555] == 43


@pytest.mark.asyncio
async def test_telegram_media_revision_change_during_generation_blocks_send():
    from test_telegram_native_sync import setup
    bot, db, client = setup()
    bot._generation_sources[555] = 40
    db.source_snapshot = AsyncMock(return_value=41)
    bot._sync_native_outgoing = AsyncMock()
    # This is the real provider-boundary version guard used by Auto and semi.
    assert not await bot._auto_send_time_ok(555)
    assert not client.sent


@pytest.mark.asyncio
async def test_send_preflight_never_starts_old_telegram_media_analysis():
    from test_telegram_native_sync import setup, message
    bot, db, client = setup()
    bot._incoming_media = SimpleNamespace(ingest=AsyncMock())
    bot._ingest_media = AsyncMock()
    client.messages = [message(100+i, '[voice]', out=False) for i in range(30)]
    client.messages.append(message(150, 'native reply'))
    await bot._sync_native_outgoing(555)
    assert db.ingested[-1]['content'] == 'native reply'
    bot._ingest_media.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['semi', 'auto'])
@pytest.mark.parametrize('understood', [None, 'Transcript: I would like to talk about tomorrow.'])
async def test_instagram_media_only_can_queue_only_with_real_analysis(mode, understood):
    from datetime import datetime, timezone
    from test_instagram_delivery import thread, settings
    from instagram_delivery import InstagramDelivery
    db = AsyncMock(model_id='model')
    db.ensure_user.return_value = {}
    db.hub.restrictions.return_value = {}
    db.known_mids.return_value = {'incoming'}
    db.processed_mids.return_value = {'incoming'}
    db.actions.return_value = []
    delivery = InstagramDelivery(db, AsyncMock())
    delivery.media = SimpleNamespace(ingest=AsyncMock(return_value=1), context=AsyncMock(return_value=understood))
    raw = thread(datetime.now(timezone.utc))
    raw['messages']['data'][0].update(message='', attachments={'data': [{'id': 'a', 'mime_type': 'audio/mp4', 'file_url': 'https://lookaside.fbsbx.com/a'}]})
    cfg = settings(); cfg['reply_mode'] = mode
    await delivery.ingest(raw, cfg)
    if understood:
        assert db.rpc.call_args.args == ('enqueue',)
        assert db.rpc.call_args.kwargs['kind'] == 'dm'
    else:
        db.rpc.assert_not_awaited()
        db.cancel_actions.assert_awaited_with('fan', 'reply_target_missing')


@pytest.mark.asyncio
async def test_fanvue_preflight_imports_context_without_paid_analysis():
    from test_fanvue_native_sync import setup
    agent, db, api, _ = setup()
    api.messages[0].update(hasMedia=True, mediaType='audio', mediaUuids=['audio-uuid'])
    agent._incoming_media = SimpleNamespace(ingest=AsyncMock(return_value=1))
    await agent._reconcile({'uuid': 'fan', 'text': ''}, dict(db.user), sync_only=True, process_media=False)
    agent._incoming_media.ingest.assert_not_awaited()

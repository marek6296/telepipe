"""Codec boundary tests: no silent truncation or unbounded attachment decoding."""
import asyncio
import json
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import social_media as media


def service():
    return media.SocialMedia(None, 'model', SimpleNamespace())


@pytest.mark.asyncio
@pytest.mark.parametrize('duration', [None, 'N/A', '-1', 'nan', '181'])
async def test_audio_rejects_unknown_or_out_of_bound_duration(monkeypatch, duration):
    run = AsyncMock(return_value=json.dumps({'format': {'duration': duration}, 'streams': [{'codec_type': 'audio'}]}).encode())
    monkeypatch.setattr(media, '_run', run)
    with pytest.raises(media.MediaError) as error:
        await service().prepare(b'fixture', 'audio')
    assert error.value.code == 'duration_limit'
    assert run.await_count == 1


@pytest.mark.asyncio
async def test_subprocess_timeout_reaps_child():
    with pytest.raises(asyncio.TimeoutError):
        await media._run('/bin/sleep', '10', timeout=.01)


@pytest.mark.asyncio
async def test_real_voice_and_video_roundtrip(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg and ffprobe are required for the real codec fixture')
    source = tmp_path / 'source.mp4'
    await media._run('ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=96x64:r=10',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000', '-t', '1', '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source))
    result = await service().prepare(source.read_bytes(), 'video')
    assert result['mime'] == 'video/mp4'
    assert result['audio'] and result['playback'] and len(result['frames']) >= 2
    assert .9 <= result['duration'] <= 1.2
    audio = await service().prepare(result['audio'], 'audio')
    assert audio['mime'] == 'audio/mpeg' and not audio['frames']
    output = tmp_path / 'output.mp4'
    output.write_bytes(result['playback'])
    await media._run('ffmpeg', '-v', 'error', '-i', str(output), '-f', 'null', '-')

@pytest.mark.asyncio
async def test_video_size_cap_is_not_reported_as_complete(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(media, 'MAX_BYTES', 100)
    async def run(*args, **kwargs):
        if args[0] == 'ffprobe':
            return json.dumps({'format': {'duration': '2'}, 'streams': [{'codec_type': 'video', 'width': 96, 'height': 64}]}).encode()
        target = Path(args[-1])
        target.write_bytes(b'x' * (100 if target.suffix == '.mp4' else 10))
        return b''
    monkeypatch.setattr(media, '_run', run)
    with pytest.raises(media.MediaError) as error:
        await service().prepare(b'fixture', 'video')
    assert error.value.code == 'file_too_large'


@pytest.mark.asyncio
async def test_incomplete_conversion_is_rejected(monkeypatch):
    from pathlib import Path
    async def run(*args, **kwargs):
        if args[0] == 'ffprobe':
            duration = '1' if str(args[-1]).endswith('video.mp4') else '2'
            return json.dumps({'format': {'duration': duration}, 'streams': [{'codec_type': 'video', 'width': 96, 'height': 64}]}).encode()
        Path(args[-1]).write_bytes(b'converted fixture')
        return b''
    monkeypatch.setattr(media, '_run', run)
    with pytest.raises(media.MediaError) as error:
        await service().prepare(b'fixture', 'video')
    assert error.value.code == 'incomplete_media'

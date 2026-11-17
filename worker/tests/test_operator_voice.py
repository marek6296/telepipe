from unittest.mock import AsyncMock
import pytest
import speech

async def test_owner_spoken_preparation_never_falls_back_to_plain_text():
    llm=type('L',(),{'structured':AsyncMock(side_effect=RuntimeError('offline'))})()
    with pytest.raises(RuntimeError):
        await speech.to_spoken(llm,'hey how was your day','calm',strict=True)

async def test_owner_spoken_uses_performance_prompt_and_preserves_tags():
    llm=type('L',(),{'structured':AsyncMock(return_value='[curious] hey... how was your day?')})()
    result=await speech.to_spoken(llm,'hey how was your day','calm',strict=True)
    assert '[curious]' in result and '...' in result
    assert 'calm' in llm.structured.call_args.args[1]

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import operator_voice


def settings():
    return SimpleNamespace(eleven_key='private',eleven_voice_id='voice',voice_strength='real',voice_tempo=1.1,
        voice_ambience_level=0.03,voice_volume_min=0.8,voice_volume_max=1.0,
        voice_lead_min=0.1,voice_lead_max=0.3,voice_tail_min=0.1,voice_tail_max=0.2)

async def test_preview_uses_prepared_speech_and_auto_audio_settings(monkeypatch):
    env=AsyncMock(return_value=(settings(),'cafe','calm at cafe'))
    monkeypatch.setattr(operator_voice,'environment',env)
    prepare=AsyncMock(return_value='[curious] hey... how was your day?')
    speak=AsyncMock(return_value=b'ogg');convert=AsyncMock(return_value=b'mp3')
    monkeypatch.setattr(speech,'to_spoken',prepare)
    monkeypatch.setattr(operator_voice.livevoice,'speak',speak)
    monkeypatch.setattr(operator_voice.livevoice,'to_mp3',convert)
    sender=SimpleNamespace(_llm=object())
    result=await operator_voice.render(sender,{'channel':'telegram','external_id':'1','text':'hey how was your day'})
    assert result==(b'ogg',b'mp3','hey... how was your day?','cafe')
    assert prepare.await_args.kwargs['strict'] is True
    assert speak.await_args.kwargs['spoken']=='[curious] hey... how was your day?'
    assert speak.await_args.args[3]=='cafe'
    assert speak.await_args.kwargs['volume_range']==(0.8,1.0)

async def test_changed_location_discards_preview(monkeypatch):
    monkeypatch.setattr(operator_voice,'environment',AsyncMock(side_effect=[(settings(),'home','calm'),(settings(),'outside','calm')]))
    monkeypatch.setattr(speech,'to_spoken',AsyncMock(return_value='hey...'))
    monkeypatch.setattr(operator_voice.livevoice,'speak',AsyncMock(return_value=b'ogg'))
    monkeypatch.setattr(operator_voice.livevoice,'to_mp3',AsyncMock(return_value=b'mp3'))
    with pytest.raises(RuntimeError,match='location changed'):
        await operator_voice.render(SimpleNamespace(_llm=object()),{'channel':'telegram','external_id':'1','text':'hey'})

async def test_expired_or_wrong_recipient_audio_cannot_be_loaded(monkeypatch):
    row={'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),
        'channel':'telegram','external_id':'1','account_scope':'primary','expected_source_id':'42','identity_id':None,'spoken':'hey','ambience':'home'}
    t=SimpleNamespace(_get=AsyncMock(return_value=[row]))
    sender=SimpleNamespace(_db=SimpleNamespace(_t=t,model_id='model'))
    command={**row,'model_id':'model','text':'hey','external_id':'other','voice_preview_id':'preview'}
    with pytest.raises(RuntimeError,match='voice_preview_changed'):
        await operator_voice.current(sender,command)
    command['external_id']='1';row['expires_at']='2000-01-01T00:00:00+00:00'
    with pytest.raises(RuntimeError,match='expired'):
        await operator_voice.current(sender,command)

async def test_preview_job_only_stores_private_audio_never_sends(monkeypatch):
    job={'id':'preview','channel':'telegram','lease_token':'lease'}
    t=SimpleNamespace(_rpc=AsyncMock(side_effect=[job,True]))
    sender=SimpleNamespace(_llm=object())
    control=SimpleNamespace(_senders={'telegram':sender})
    monkeypatch.setattr(operator_voice,'render',AsyncMock(return_value=(b'ogg',b'mp3','hey','home')))
    upload=AsyncMock()
    monkeypatch.setattr(operator_voice,'SocialMedia',lambda *a:SimpleNamespace(upload=upload))
    await operator_voice.VoicePreviews(t,'model','worker',control).tick()
    assert [c.args[0] for c in t._rpc.await_args_list]==['social_claim_voice','social_finish_voice']
    assert [c.args[0] for c in upload.await_args_list]==['model/voice-previews/preview.ogg','model/voice-previews/preview.mp3']
    assert t._rpc.await_args.args[1]['p_result']['spoken']=='hey'

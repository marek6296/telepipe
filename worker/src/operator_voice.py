"""Private owner voice previews: performance preparation, existing voice render,
source-fenced storage. This module never marks seen or sends a customer message.
"""
import asyncio
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import den
import livevoice
import speech
from behavior import Behavior
from social_media import SocialMedia, BUCKET

async def environment(sender, channel, external):
    db=sender._db
    raw=await (db.get_behavior() if channel=='telegram' else db.behavior())
    behavior=Behavior.from_row(raw)
    schedule=den.Rozvrh.from_row(await (db.get_schedule() if channel=='telegram' else db.schedule()))
    now=datetime.now(ZoneInfo(behavior.active_tz or 'America/Los_Angeles'))
    hub=getattr(db,'hub',None)
    if not hub:
        raise RuntimeError('The shared day is unavailable. Try again.')
    block,mood=await hub.day(now,schedule)
    ambience=den.where(block,behavior.voice_ambience or 'home')
    rows=await (db.recent_messages(int(external),12) if channel=='telegram' else db.history(external,12))
    linked=await hub.context(channel,external)
    hint=f'Current shared mood: {mood}. Current location: {ambience}. Local time: {now.isoformat()}.\n'
    hint+='Conversation is context for tone ONLY; do not add any of its facts to the supplied reply.\n'+str(rows)[-10000:]+'\n'+str(linked)[-6000:]
    return behavior,ambience,hint

async def render(sender,job):
    behavior,ambience,hint=await environment(sender,job['channel'],job['external_id'])
    if not behavior.eleven_key or not behavior.eleven_voice_id:
        raise RuntimeError('Configure the model’s ElevenLabs voice before generating a voice reply.')
    if re.search(r'https?://|\bwww\.',job['text'],re.I):
        raise RuntimeError('Send links as text instead of reading them in a voice note.')
    spoken=await speech.to_spoken(sender._llm,job['text'],hint,strict=True)
    if not spoken:
        raise RuntimeError('Spoken preparation returned no speech. Generate again.')
    # Preserve useful performance cues; strip model prose/unsupported SSML markup.
    if '<' in spoken or '>' in spoken:
        raise RuntimeError('The spoken script was invalid. Generate again.')
    ogg=await livevoice.speak(job['text'],behavior.eleven_key,behavior.eleven_voice_id,
        ambience,behavior.voice_strength or 'rough',tempo=float(behavior.voice_tempo or 1.12),
        level=float(behavior.voice_ambience_level or 0.05),spoken=spoken,
        volume_range=(behavior.voice_volume_min,behavior.voice_volume_max),
        lead_range=(behavior.voice_lead_min,behavior.voice_lead_max),tail_range=(behavior.voice_tail_min,behavior.voice_tail_max))
    if not ogg:
        raise RuntimeError('Voice generation failed. No text or audio was sent. Try again.')
    mp3=await livevoice.to_mp3(ogg)
    if not mp3:
        raise RuntimeError('Voice conversion failed. Try again.')
    _,current,_=await environment(sender,job['channel'],job['external_id'])
    if current!=ambience:
        raise RuntimeError('Her current location changed. Generate a fresh voice preview.')
    transcript=re.sub(r'\[[^\]]{1,80}\]',' ',spoken)
    transcript=re.sub(r'\s+',' ',transcript).strip()
    return ogg,mp3,transcript,ambience

class VoicePreviews:
    def __init__(self,t,model,worker,control):self.t,self.model,self.worker,self.control=t,model,worker,control
    async def run(self):
        while True:
            try:await self.tick()
            except Exception:pass # Never log voice scripts, keys or signed URLs.
            await asyncio.sleep(1)
    async def tick(self):
        job=await self.t._rpc('social_claim_voice',{'p_model':self.model,'p_worker':self.worker})
        if not job:return
        result={}
        try:
            sender=self.control._senders.get(job['channel'])
            if not sender:raise RuntimeError('This channel is not connected.')
            ogg,mp3,spoken,ambience=await render(sender,job)
            store=SocialMedia(self.t,self.model,sender._llm)
            prefix=f'{self.model}/voice-previews/{job["id"]}'
            await store.upload(prefix+'.ogg',ogg,'audio/ogg')
            await store.upload(prefix+'.mp3',mp3,'audio/mpeg')
            result={'spoken':spoken,'ambience':ambience,'ogg_path':prefix+'.ogg','mp3_path':prefix+'.mp3'}
        except RuntimeError as exc:result={'error':str(exc)[:200]}
        except Exception:result={'error':'Could not prepare this voice preview. Nothing was sent. Generate again.'}
        await self.t._rpc('social_finish_voice',{'p_model':self.model,'p_worker':self.worker,'p_id':job['id'],'p_lease':job['lease_token'],'p_result':result})

async def current(sender,command):
    """Metadata-only validation, repeated at the final delivery boundary."""
    db=sender._db;t=db._t
    rows=await t._get('/social_voice_previews',{'model_id':'eq.'+command['model_id'],'id':'eq.'+str(command.get('voice_preview_id') or ''),'status':'eq.ready','select':'*'})
    if not rows:raise RuntimeError('voice_preview_unavailable')
    row=rows[0]
    if datetime.fromisoformat(row['expires_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc):raise RuntimeError('voice_preview_expired')
    for key in ('channel','external_id','account_scope','expected_source_id','identity_id'):
        if row.get(key)!=command.get(key):raise RuntimeError('voice_preview_changed')
    if row['spoken']!=command['text']:raise RuntimeError('voice_preview_changed')
    _,ambience,_=await environment(sender,command['channel'],command['external_id'])
    if ambience!=row['ambience']:raise RuntimeError('voice_environment_changed')
    return row

async def load(sender,command,extension='ogg'):
    row=await current(sender,command)
    t=sender._db._t
    path=row.get(extension+'_path')
    expected=f'{command["model_id"]}/voice-previews/{row["id"]}.{extension}'
    if path!=expected:raise RuntimeError('voice_preview_unavailable')
    base=str(t._client.base_url).split('/rest/v1')[0]
    response=await t._client.get(f'{base}/storage/v1/object/authenticated/{BUCKET}/{path}',timeout=40)
    response.raise_for_status()
    if not response.content or len(response.content)>10*1024*1024:raise RuntimeError('voice_preview_unavailable')
    return response.content

async def fanvue_media(sender,command):
    """Upload the approved preview only, before seen/send; await playable media."""
    from fanvue_owner_media import call
    mp3=await load(sender,command,'mp3')
    t=sender._db._t
    query={'model_id':'eq.'+command['model_id'],'id':'eq.'+command['voice_preview_id']}
    row=(await t._get('/social_voice_previews',{**query,'select':'fanvue_media_uuid'}))[0]
    media=row.get('fanvue_media_uuid')
    if not media:
        cfg=await sender._db.settings()
        if not cfg.get('connected') or 'fanvue:'+str(cfg.get('creator_uuid') or '')!=command['account_scope']:
            raise RuntimeError('fanvue_disconnected')
        media=await sender._api.upload(cfg['creator_uuid'],mp3,'voice-'+command['voice_preview_id']+'.mp3','audio')
        if not media:raise RuntimeError('voice_upload_failed')
        await t._patch('/social_voice_previews',query,{'fanvue_media_uuid':media})
    for _ in range(45):
        body=await call(sender._api,'GET','/media/'+media,params={'variants':'thumbnail'})
        item=body.get('data',body)
        if item.get('status')=='ready':
            await sender._db.upsert_media([{'media_uuid':media,'kind':'audio'}])
            return media
        if item.get('status')=='error':raise RuntimeError('voice_processing_failed')
        await asyncio.sleep(3)
    raise RuntimeError('voice_still_processing')


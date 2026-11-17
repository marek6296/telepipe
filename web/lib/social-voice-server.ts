import 'server-only';
import {createHash} from 'node:crypto';
import {socialContext,socialContact,socialPending} from '@/lib/social-server';
import {SocialError,UUID,validateSocialCommand} from '@/lib/social-policy';
import type {SocialVoiceRequest,SocialVoiceResult,SocialVoicePreview} from '@/lib/social-types';
export async function loadVoicePreview(modelId:string,request:SocialVoiceRequest):Promise<SocialVoiceResult>{
 const ctx=await socialContext(modelId);
 if(!request || !UUID.test(request.id || ''))throw new SocialError('Invalid voice request.');
 const contact=await socialContact(ctx,request.contactKey);
 if(!['telegram','fanvue'].includes(contact.channel))throw new SocialError('Voice notes are available on Telegram and Fanvue.');
 let row=(await ctx.db.from('social_voice_previews').select('*').eq('model_id',modelId).eq('id',request.id).eq('requested_by',ctx.userId).maybeSingle());
 if(row.error)throw new SocialError('Could not load the voice preview.',503);
 if(!row.data){
  if(!request.input)throw new SocialError('This preview is unavailable. Generate a new one.',404);
  const pending=await socialPending(ctx,contact);
  const valid=validateSocialCommand({...request.input,requestId:request.id,operation:'send_text'},contact,pending);
  const text=valid.text?.trim() || '';
  if(text.length>1000)throw new SocialError('Voice replies can contain at most 1,000 characters. Shorten the message.');
  if(/https?:\/\/|\bwww\./i.test(text))throw new SocialError('Send links as text instead of reading them in a voice note.');
  const key=createHash('sha256').update(JSON.stringify([contact.key,contact.accountScope,contact.lastMessageId,contact.identityId,contact.identityUpdatedAt,pending?.id,pending?.suggestions,text])).digest('hex');
  const result=await ctx.db.rpc('social_request_voice',{p_model:modelId,p_owner:ctx.userId,p_id:request.id,p_regenerate:request.regenerate===true,p_payload:{channel:contact.channel,external_id:contact.externalId,account_scope:contact.accountScope,
    expected_source_id:contact.lastMessageId,identity_id:contact.identityId,identity_updated_at:contact.identityUpdatedAt,pending_id:pending?.id || null,expected_suggestions:pending?.suggestions || null,text,cache_key:key}});
  if(result.error || !result.data)throw new SocialError(result.error?.code==='P0001' ? 'The conversation changed or other previews are still preparing. Try again shortly.' : 'Could not confirm the voice request. Open it again to check.',result.error?.code==='P0001'?409:503);
  row={...row,data:result.data,error:null};
 }
 const v=row.data!;
 if(request.input && (v.text!==request.input.text?.trim() || v.expected_source_id!==request.input.expectedSourceId || v.account_scope!==request.input.expectedAccountScope || v.identity_id!==request.input.identityId))throw new SocialError('This voice request belongs to a different reply. Generate a fresh preview.',409);
 if(v.pending_id){const pending=await socialPending(ctx,contact);if(!pending || pending.id!==v.pending_id || JSON.stringify(pending.suggestions)!==JSON.stringify(v.expected_suggestions))throw new SocialError('The suggestions changed. Generate a fresh voice preview.',409);}

 if(v.channel!==contact.channel || v.external_id!==contact.externalId || v.account_scope!==contact.accountScope || v.expected_source_id!==contact.lastMessageId || v.identity_id!==contact.identityId
  || Date.parse(v.identity_updated_at || '')!==Date.parse(contact.identityUpdatedAt || '') && !(v.identity_updated_at===null&&contact.identityUpdatedAt===null))throw new SocialError('The conversation changed. Generate a fresh voice preview.',409);
 if(Date.parse(v.expires_at)<=Date.now())throw new SocialError('This voice preview expired. Generate a fresh one.',409);
 let url:string|null=null;
 const expected=`${modelId}/voice-previews/${v.id}.mp3`;
 if(v.status==='ready' && v.mp3_path===expected){
  const signed=await ctx.db.storage.from('social-media').createSignedUrl(expected,300);
  if(signed.error)throw new SocialError('Could not load voice playback. Try reopening the preview.',503);
  url=signed.data.signedUrl;
 }
 const preview:SocialVoicePreview={id:v.id,status:v.status,text:v.text,spoken:v.spoken,ambience:v.ambience,playbackUrl:url,error:v.error,expiresAt:v.expires_at};
 return {preview};
}

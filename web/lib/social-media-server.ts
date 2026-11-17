import 'server-only';
import { selectSocialMedia } from '@/lib/social-media-policy';
import type { SocialContext } from '@/lib/social-server';
import type { SocialContact, SocialMedia } from '@/lib/social-types';

const BUCKET='social-media';
const COLUMNS='id,model_id,channel,external_id,account_scope,message_id,kind,mime_type,storage_path,transcript,description,status,error,duration_seconds,original_content';
// Stable URLs keep a playing element from restarting on each five-second inbox
// refresh. Authorization is always checked before this cache can be consulted.
const playbackCache=new Map<string,{url:string;expires:number}>();
const SIGNED_SECONDS=300;

export async function loadSocialMedia(ctx:SocialContext,contact:SocialContact,messageIds:string[]):Promise<Record<string,{media:SocialMedia[];originalContent:string|null}>> {
  if(!messageIds.length) return {};
  const result=await ctx.db.from('social_message_media').select(COLUMNS)
    .eq('model_id',ctx.model.id).eq('channel',contact.channel).eq('external_id',contact.externalId)
    .eq('account_scope',contact.accountScope).in('message_id',messageIds).order('created_at',{ascending:true});
  if(result.error) {
    // A media processing/storage outage must not hide the authoritative text
    // conversation or its existing replies. The next normal poll retries it.
    return {};
  }
  const rows=selectSocialMedia((result.data || []) as Record<string,unknown>[],{
    modelId:ctx.model.id,channel:contact.channel,externalId:contact.externalId,
    accountScope:contact.accountScope,messageIds,
  });
  const now=Date.now();
  for(const [path,item] of playbackCache) if(item.expires<=now) playbackCache.delete(path);
  const paths=[...new Set(rows.map(r=>r.storagePath).filter((p):p is string=>!!p && !playbackCache.has(p)))];
  if(paths.length) {
    try {
    const signed=await ctx.db.storage.from(BUCKET).createSignedUrls(paths,SIGNED_SECONDS);
    if(!signed.error) for(const item of signed.data || []) {
      if(item.path && paths.includes(item.path) && item.signedUrl && !item.error) {
        // Only the trusted Storage client supplies URLs, never provider metadata.
        try {
          if(new URL(item.signedUrl).protocol!=='https:') continue;
          playbackCache.set(item.path,{url:item.signedUrl,expires:now+(SIGNED_SECONDS-45)*1000});
        } catch { /* Invalid Storage responses cannot become media sources. */ }
      }
    }
    } catch { /* Transcript and conversation remain available during storage outages. */ }
  }
  while(playbackCache.size>2000) playbackCache.delete(playbackCache.keys().next().value!);
  const grouped:Record<string,{media:SocialMedia[];originalContent:string|null}>={};
  for(const row of rows) {
    row.media.playbackUrl=row.storagePath ? playbackCache.get(row.storagePath)?.url || null : null;
    (grouped[row.messageId] ||= {media:[],originalContent:row.originalContent}).media.push(row.media);
  }
  return grouped;
}

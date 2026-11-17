import 'server-only';
import {socialContext,requireSocialChannel} from '@/lib/social-server';
import {SocialError} from '@/lib/social-policy';
import {mediaJob} from '@/lib/fanvue-owner-policy';
import type {FanvueMediaJobResult} from '@/lib/social-types';
function canonical(v:unknown):string {
 if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';
 if(v && typeof v==='object')return '{'+Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,value])=>JSON.stringify(k)+':'+canonical(value)).join(',')+'}';
 return JSON.stringify(v);
}
export async function ownerMediaRequest(modelId:string,scope:string,input:unknown):Promise<FanvueMediaJobResult>{
 const ctx=await socialContext(modelId);requireSocialChannel(ctx,'fanvue');
 const cfg=await ctx.db.from('fanvue').select('connected,creator_uuid').eq('model_id',modelId).single();
 if(cfg.error || !cfg.data.connected || scope!==`fanvue:${cfg.data.creator_uuid}`)throw new SocialError('The Fanvue connection changed. Reopen this chat.',409);
 let request;try{request=mediaJob(input);}catch(error){throw new SocialError(error instanceof Error?error.message:'Invalid media request.');}
 const {id,action,...args}=request;
 const prior=await ctx.db.from('social_fanvue_requests').select('*').eq('model_id',modelId).eq('id',id).maybeSingle();
 if(prior.error)throw new SocialError('Could not check this media request.',503);
 if(prior.data){
  if(Date.parse(prior.data.expires_at)<=Date.now())throw new SocialError('This media request expired. Reload Vault or select the file again.',409);
  if(prior.data.account_scope!==scope || prior.data.action!==action || canonical(prior.data.input)!==canonical(args))throw new SocialError('Media request changed. Reopen the picker.',409);
  return {job:{id,status:prior.data.status,output:prior.data.output,error:prior.data.error}};
 }
 const pending=await ctx.db.from('social_fanvue_requests').select('id',{count:'exact',head:true}).eq('model_id',modelId).in('status',['queued','working']).gt('expires_at',new Date().toISOString());
 if(pending.error)throw new SocialError('Could not check media requests.',503);
 if((pending.count || 0)>=12)throw new SocialError('Other media requests are still processing. Try again shortly.',429);
 const result=await ctx.db.from('social_fanvue_requests').insert({id,model_id:modelId,account_scope:scope,action,input:args}).select('*').single();
 if(result.error)throw new SocialError('Could not confirm the request. Retry it with the same ID.',503);
 return {job:{id,status:result.data.status,output:result.data.output,error:result.data.error}};
}

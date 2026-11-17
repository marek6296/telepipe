"use server";

import { revalidatePath } from "next/cache";
import { mapSocialCommand, socialContact, socialContext, socialErrorMessage, socialPending, requireSocialChannel, COMMAND_COLUMNS } from "@/lib/social-server";
import { parseContactKey, SocialError, UUID, validateSocialCommand } from "@/lib/social-policy";
import type { SocialChannel, SocialCommandInput, SocialContact, SocialMode, SocialResult } from "@/lib/social-types";

export async function submitSocialCommand(modelId: string, input: SocialCommandInput): Promise<SocialResult> {
  try {
    const ctx = await socialContext(modelId);
    if (!input || !UUID.test(input.requestId || "")) throw new SocialError("Invalid request ID.");
    const {channel,externalId} = parseContactKey(input.contactKey);
    requireSocialChannel(ctx,channel);
    // A lost HTTP response must return the original outcome, even after sending
    // changes the source message. Never re-validate it as a new instruction.
    const existing = await ctx.db.from("social_commands").select(COMMAND_COLUMNS).eq("model_id",modelId).eq("idempotency_key",input.requestId).maybeSingle();
    if (existing.error) throw new SocialError("Could not check this request.",503);
    if (existing.data) {
      const c = existing.data;
      if (c.operation !== input.operation || c.channel !== channel || c.external_id !== externalId || c.account_scope !== input.expectedAccountScope
        || c.pending_id !== (input.pendingId || null) || JSON.stringify(c.expected_suggestions) !== JSON.stringify(input.expectedSuggestions || null)
        || c.expected_source_id !== input.expectedSourceId || c.identity_id !== input.identityId
        || (c.voice_preview_id || undefined)!==input.voicePreviewId
        || JSON.stringify(c.media_uuids || []) !== JSON.stringify(input.mediaUuids || []) || Number(c.price_cents || 0) !== Number(input.priceCents || 0)
        || c.identity_updated_at !== input.identityUpdatedAt || c.text !== (input.text || "") || c.brief !== (input.brief || ""))
        throw new SocialError("This request ID belongs to a different action. Refresh before retrying.",409);
      return {command:mapSocialCommand(c)};
    }
    const contact = await socialContact(ctx,input.contactKey);
    const pending = await socialPending(ctx,contact);
    const valid = validateSocialCommand(input,contact,pending);
    const {data,error} = valid.operation==="send_voice" ? await ctx.db.rpc("social_enqueue_voice",{p_model:modelId,p_owner:ctx.userId,p_key:valid.requestId,p_preview:valid.voicePreviewId,p_price:valid.priceCents || 0,p_channel:contact.channel,p_external:contact.externalId,p_scope:contact.accountScope,p_source:valid.expectedSourceId,p_text:valid.text}) : valid.operation==="send_media" ? await ctx.db.rpc("social_enqueue_fanvue_media",{
      p_model:modelId,p_owner:ctx.userId,p_key:valid.requestId,p_external:contact.externalId,p_scope:contact.accountScope,p_source:valid.expectedSourceId,
      p_identity:valid.identityId,p_revision:valid.identityUpdatedAt,p_text:valid.text || "",p_media:valid.mediaUuids,p_price:valid.priceCents,p_pending:valid.pendingId || null,p_suggestions:valid.expectedSuggestions || null,
    }) : await ctx.db.rpc("social_enqueue",{p_model:modelId,p_requested_by:ctx.userId,p_key:valid.requestId,p_operation:valid.operation,
      p_channel:contact.channel,p_external:contact.externalId,p_scope:contact.accountScope,p_pending:valid.pendingId || null,p_suggestions:valid.expectedSuggestions || null,
      p_source:valid.expectedSourceId,p_identity:valid.identityId,p_identity_updated_at:valid.identityUpdatedAt,p_text:valid.text || "",p_brief:valid.brief || ""});
    if (error) {
      const rejected = error.code === "P0001" || error.code === "42501" || /^(22|23)/.test(error.code || "");
      throw new SocialError(rejected ? "The conversation or suggestions changed. Refresh and review them before trying again."
        : "The request outcome could not be confirmed. Retry the same request to check it safely.",rejected ? 409 : 503);
    }
    if (!data?.id) throw new SocialError("The request outcome could not be confirmed. Retry the same request to check it safely.",503);
    return {command:mapSocialCommand(data),message:valid.operation === "regenerate" ? "New suggestions requested." : "Reply queued."};
  } catch (error) { return {error:socialErrorMessage(error),retryable:!(error instanceof SocialError) || error.status >= 500}; }
}

export async function setSocialMode(modelId: string, channel: SocialChannel, mode: SocialMode): Promise<SocialResult> {
  try {
    const ctx = await socialContext(modelId);
    requireSocialChannel(ctx,channel);
    if (!["off","semi","auto"].includes(mode)) throw new SocialError("Choose a reply mode.");
    const table = channel === "telegram" ? "settings" : channel;
    const patch = channel === "telegram" ? {tg_reply_mode:mode,tg_fallback_minutes:null}
      : channel === "fanvue" ? {reply_mode:mode,fallback_minutes:null,enabled:true}
      : {reply_mode:mode,enabled:mode !== "off"};
    const result = await ctx.db.from(table).update(patch).eq("model_id",modelId).select("model_id").maybeSingle();
    if (result.error || !result.data) throw new SocialError("Could not update this channel. Check its connection first.",503);
    revalidatePath(`/app/m/${modelId}`);
    return {message:mode === "off" ? "Manual replies enabled." : mode === "semi" ? "Suggestions will wait for your approval." : "Automatic replies follow the model’s schedule."};
  } catch (error) { return {error:socialErrorMessage(error)}; }
}

export async function setSocialTakeover(modelId: string, contactKey: string, takeover: boolean): Promise<SocialResult> {
  try {
    const ctx = await socialContext(modelId);
    if (typeof takeover !== "boolean") throw new SocialError("Choose who should reply.");
    const contact = await socialContact(ctx,contactKey);
    const result = await ctx.db.rpc("social_set_takeover",{p_model:modelId,p_channel:contact.channel,p_external:contact.externalId,p_takeover:takeover});
    if (result.error || result.data !== true) throw new SocialError("Could not update this conversation. Refresh and try again.",409);
    return {message:takeover ? "You are handling this conversation." : "This conversation follows the channel’s reply mode."};
  } catch (error) { return {error:socialErrorMessage(error)}; }
}

async function ensureIdentity(ctx: Awaited<ReturnType<typeof socialContext>>, contact: SocialContact): Promise<string> {
  if (contact.identityId) return contact.identityId;
  const {data,error} = await ctx.db.rpc("conversation_ensure_identity",{p_model:ctx.model.id,p_platform:contact.channel,p_external:contact.externalId,p_scope:contact.channel === "instagram" ? contact.accountScope : "primary",p_username:contact.username,p_name:contact.displayName});
  if (error || !data?.id) throw new SocialError("Could not prepare the account link.",503);
  return data.id;
}

export async function linkSocialContacts(modelId: string, firstKey: string, secondKey: string): Promise<SocialResult> {
  try {
    const ctx = await socialContext(modelId);
    const [first,second] = await Promise.all([socialContact(ctx,firstKey),socialContact(ctx,secondKey)]);
    if (first.key === second.key || first.channel === second.channel) throw new SocialError("Choose an account on another channel.");
    if (first.personId && first.personId === second.personId) return {message:"These accounts are already linked."};
    const firstId = await ensureIdentity(ctx,first);
    const secondId = await ensureIdentity(ctx,second);
    const {error} = await ctx.db.rpc("conversation_pair",{p_model:modelId,p_identity:firstId,p_other:secondId,p_decision:"verified",p_evidence:{source:"owner_social_sites",confirmed_by:ctx.userId}});
    if (error) throw new SocialError("Could not link these accounts. Refresh and try again.",409);
    return {message:"Accounts linked. New replies will use their shared history."};
  } catch (error) { return {error:socialErrorMessage(error)}; }
}

export async function unlinkSocialContact(modelId: string, contactKey: string): Promise<SocialResult> {
  try {
    const ctx = await socialContext(modelId);
    const contact = await socialContact(ctx,contactKey);
    if (!contact.identityId || !contact.personId) throw new SocialError("This account is not linked.");
    const {data,error} = await ctx.db.from("social_contact_summaries").select("identity_id").eq("model_id",modelId).eq("person_id",contact.personId).in("channel",ctx.channels).neq("identity_id",contact.identityId).limit(1).maybeSingle();
    if (error || !data?.identity_id) throw new SocialError("There is no other linked account to separate.");
    const result = await ctx.db.rpc("conversation_pair",{p_model:modelId,p_identity:contact.identityId,p_other:data.identity_id,p_decision:"rejected",p_evidence:{source:"owner_social_sites",confirmed_by:ctx.userId}});
    if (result.error) throw new SocialError("Could not separate this account. Refresh and try again.",409);
    return {message:"Account separated. Stale suggestions have been removed."};
  } catch (error) { return {error:socialErrorMessage(error)}; }
}

export async function skipSocialPending(modelId: string, pendingId: string, expectedSuggestions: string[]): Promise<SocialResult> {
  try {
    const ctx = await socialContext(modelId);
    if (!UUID.test(pendingId) || !Array.isArray(expectedSuggestions) || expectedSuggestions.some(s => typeof s !== "string")) throw new SocialError("Invalid suggestion.");
    const {data,error} = await ctx.db.from("pending_replies").select("channel,conv_key").eq("model_id",modelId).eq("id",pendingId).maybeSingle();
    if (error || !data) throw new SocialError("This suggestion is no longer available.",409);
    requireSocialChannel(ctx,data.channel as SocialChannel);
    await socialContact(ctx,`${data.channel}:${data.channel === "instagram" ? data.conv_key.split(":")[0] : data.conv_key}`);
    const result = await ctx.db.rpc("social_skip_pending",{p_model:modelId,p_pending:pendingId,p_expected:expectedSuggestions});
    if (result.error || result.data !== true) throw new SocialError("These suggestions changed. Refresh before skipping them.",409);
    return {message:"Suggestion skipped."};
  } catch (error) { return {error:socialErrorMessage(error)}; }
}

export async function getSocialPersonBrief(modelId:string,contactKey:string,refresh=false):Promise<import('@/lib/social-types').SocialBriefResult> {
  try {
    if(typeof refresh!=='boolean')throw new SocialError('Invalid summary request.');
    const {personBrief}=await import('@/lib/social-brief-server');
    return await personBrief(modelId,contactKey,refresh);
  } catch(error) {return {error:socialErrorMessage(error)};}
}

export async function fanvueOwnerMedia(modelId:string,scope:string,input:unknown):Promise<import('@/lib/social-types').FanvueMediaJobResult> {
 try {
  const {ownerMediaRequest}=await import('@/lib/fanvue-owner-server');
  return await ownerMediaRequest(modelId,scope,input);
 } catch(error){return {error:socialErrorMessage(error)};}
}

export async function socialVoicePreview(modelId:string,request:import('@/lib/social-types').SocialVoiceRequest):Promise<import('@/lib/social-types').SocialVoiceResult>{
 try{const {loadVoicePreview}=await import('@/lib/social-voice-server');return await loadVoicePreview(modelId,request);}catch(error){return {error:socialErrorMessage(error)};}
}

export async function dismissSocialCommand(modelId:string,contactKey:string,commandId:string):Promise<SocialResult>{
 try{
  const ctx=await socialContext(modelId);
  if(!UUID.test(commandId || ""))throw new SocialError("Invalid request.");
  const contact=await socialContact(ctx,contactKey);
  const result=await ctx.db.rpc("social_dismiss_command",{p_model:modelId,p_owner:ctx.userId,p_command:commandId,p_channel:contact.channel,p_external:contact.externalId,p_scope:contact.accountScope});
  if(result.error || result.data!==true)throw new SocialError("Only a confirmed unsent attempt or an unused owner draft can be removed. Refresh the conversation.",409);
  return {message:"Removed from chat."};
 }catch(error){return {error:socialErrorMessage(error)};}
}

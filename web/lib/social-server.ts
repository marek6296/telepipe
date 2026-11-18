import "server-only";

import { loadSocialMedia } from "@/lib/social-media-server";

import { getModel } from "@/lib/models";
import { modelTypeHasTab } from "@/lib/model-types";
import { createClient, createServiceClient, getUser } from "@/lib/supabase/server";
import { getTelegramConnection } from "@/lib/telegram";
import { miniSocialContext } from "@/lib/telegram-mini-server";
import { authorizeSocialOwner, groupSocialPeople, mapSocialContact, mapSocialMessage, parseContactKey, parseSocialQuery, SocialError, str, UUID } from "@/lib/social-policy";
import type { SocialChannel, SocialChannelState, SocialCommand, SocialContact, SocialFilter, SocialMode, SocialPending, SocialSnapshot, SocialThread } from "@/lib/social-types";

type Row = Record<string, unknown>;
export const CONTACT_COLUMNS = "model_id,channel,external_id,account_scope,identity_id,person_id,identity_status,candidate_id,identity_updated_at,display_name,username,avatar_url,ai_enabled,human_takeover,summary,spent_cents,last_incoming_at,last_reply_at,last_message_id,last_message_role,last_message_text,last_message_at,last_activity_at,pending_id,needs_reply";
export const COMMAND_COLUMNS = "id,ui_dismissed_at,idempotency_key,voice_preview_id,media_uuids,price_cents,operation,channel,external_id,account_scope,pending_id,expected_suggestions,expected_source_id,identity_id,identity_updated_at,text,brief,status,result,reason,created_at";
const PENDING_COLUMNS = "id,channel,conv_key,suggestions,incoming_preview,hint,created_at,updated_at";

/** Service access is created only after verified authentication + strict ownership. */
export async function socialContext(modelId: string) {
  if (!UUID.test(modelId)) throw new SocialError("This model is not available.", 404);
  const mini = await miniSocialContext(modelId);
  if (mini) return mini;
  const user = await getUser();
  if (!user) throw new SocialError("Sign in to continue.", 401);
  const client = await createClient();
  const [model, roleResult] = await Promise.all([
    getModel(modelId), client.from("accounts").select("role").eq("id", user.id).maybeSingle(),
  ]);
  if (roleResult.error) throw new SocialError("Could not verify your access.", 503);
  const channels = authorizeSocialOwner(model, user.id, str(roleResult.data?.role));
  if (!model || !modelTypeHasTab(model.model_type, "social")) throw new SocialError("This workspace is not available.", 404);
  return {model, userId: user.id, channels: channels.filter(c => modelTypeHasTab(model.model_type, c)), db: createServiceClient()};
}
export type SocialContext = Awaited<ReturnType<typeof socialContext>>;

export function requireSocialChannel(ctx: SocialContext, channel: SocialChannel) {
  if (!ctx.channels.includes(channel)) throw new SocialError("This channel is not available.", 404);
}
function checked<T>({data, error}: {data: T; error: unknown}, message: string): T {
  if (error) throw new SocialError(message, 503);
  return data;
}
const mode = (v: unknown): SocialMode => v === "semi" || v === "auto" ? v : "off";
const time = (v: unknown) => { const n = Number(v); return `${Math.floor(n/60).toString().padStart(2,"0")}:${(n%60).toString().padStart(2,"0")}`; };

export async function loadSocialSnapshot(modelId: string, input: {search?: string; channel?: SocialChannel | "all"; filter?: SocialFilter; offset?: number} = {}): Promise<SocialSnapshot> {
  const loadedAt=new Date().toISOString();
  const ctx = await socialContext(modelId);
  const query = parseSocialQuery(new URLSearchParams(Object.entries(input).map(([k,v]) => [k,String(v)])));
  if (query.channel !== "all") requireSocialChannel(ctx, query.channel);
  const {db,model} = ctx;
  const [inboxResult, settingsResult, fvResult, igResult, behaviorResult, tg] = await Promise.all([
    db.rpc("social_inbox", {p_model:modelId,p_search:query.search,p_channel:query.channel === "all" ? "" : query.channel,p_filter:query.filter,p_limit:30,p_offset:query.offset,p_allow_instagram:ctx.channels.includes("instagram")}),
    db.from("settings").select("tg_reply_mode,ai_paused,paused_until").eq("model_id",modelId).maybeSingle(),
    db.from("fanvue").select("connected,enabled,handle,reply_mode,last_error,updated_at").eq("model_id",modelId).maybeSingle(),
    ctx.channels.includes("instagram") ? db.from("instagram").select("connected,enabled,username,reply_mode,sync_status,sync_completed_at,last_error,circuit_until,circuit_reason").eq("model_id",modelId).maybeSingle() : Promise.resolve({data:null,error:null}),
    db.from("behavior").select("active_tz,active_start_min,active_end_min").eq("model_id",modelId).maybeSingle(),
    getTelegramConnection(model),
  ]);
  const inbox = checked(inboxResult,"Could not load the inbox.") as {contacts:Row[];total:number};
  const contacts = (inbox?.contacts || []).map(mapSocialContact);
  const counts = checked(await db.rpc("social_waiting_message_counts",{p_model:modelId,p_owner:ctx.userId,p_contacts:contacts.map(c=>({channel:c.channel,externalId:c.externalId,accountScope:c.accountScope}))}),"Could not load waiting message counts.") as Record<string,number>;
  contacts.forEach(contact=>{contact.waitingMessageCount=Math.max(0,Number(counts?.[contact.key] || 0));});
  // Read durable in-flight sends, not proposal generation. Page the result so
  // a large operator queue cannot hide another contact's progress.
  const externalIds=[...new Set(contacts.map(c=>c.externalId))];
  const sending:Row[]=[];
  if(externalIds.length)for(let offset=0;;offset+=1000){
    const rows=checked(await db.from("social_commands").select("id,channel,external_id,account_scope")
      .eq("model_id",modelId).neq("operation","regenerate").in("status",["queued","working","sending"])
      .in("external_id",externalIds).in("channel",ctx.channels).order("id").range(offset,offset+999),"Could not load reply progress.") as Row[];
    sending.push(...rows);if(rows.length<1000)break;
  }
  contacts.forEach(contact=>{contact.replyInProgress=sending.some(c=>c.channel===contact.channel && c.external_id===contact.externalId && c.account_scope===contact.accountScope);});
  const settings = checked(settingsResult,"Could not load reply settings.");
  const fv = checked(fvResult,"Could not load Fanvue connection.");
  const ig = checked(igResult,"Could not load Instagram connection.");
  const behavior = checked(behaviorResult,"Could not load the schedule.");
  const running = model.status === "active" && Boolean(model.claimed_by) && Date.now()-Date.parse(model.heartbeat_at || "") < 90_000;
  const base = `/app/m/${modelId}`;
  const channels: SocialChannelState[] = ctx.channels.map(channel => {
    const config = channel === "instagram" ? ig : fv;
    const connected = channel === "telegram" ? tg.connected : config?.connected === true;
    const activeMode = channel === "telegram" ? mode(settings?.tg_reply_mode) : config?.enabled === false ? "off" : mode(config?.reply_mode);
    const circuit = channel === "instagram" && Date.parse(ig?.circuit_until || "") > Date.now();
    return {channel,available:true,connected,handle:channel === "telegram" ? (tg.phone || "Telegram account") : str(channel === "instagram" ? ig?.username : fv?.handle),
      mode:activeMode,connectHref:`${base}/${channel}`,settingsHref:`${base}/${channel}/settings`,
      syncStatus:channel === "instagram" ? str(ig?.sync_status) || "not_started" : running && connected ? "live" : "offline",
      lastSyncAt:channel === "instagram" ? ig?.sync_completed_at || null : running ? model.heartbeat_at : null,
      notice:circuit ? "Instagram is temporarily paused by a delivery safeguard." : config?.last_error ? "Connection needs attention. Open channel settings." : !running ? "Agent is offline. Replies will wait until it is running." : null};
  });
  return {modelId,modelName:model.name,channels,people:groupSocialPeople(contacts),total:Number(inbox?.total || 0),offset:query.offset,pageSize:30,loadedAt,
    agent:{running,status:model.status,paused:settings?.ai_paused === true || Date.parse(settings?.paused_until || "") > Date.now(),timezone:behavior?.active_tz || "America/Los_Angeles",schedule:behavior ? `${time(behavior.active_start_min)}–${time(behavior.active_end_min)}` : "Configured daily schedule"}};
}

export async function socialContact(ctx: SocialContext, key: string): Promise<SocialContact> {
  const {channel,externalId} = parseContactKey(key);
  requireSocialChannel(ctx,channel);
  const result = await ctx.db.from("social_contact_summaries").select(CONTACT_COLUMNS).eq("model_id",ctx.model.id).eq("channel",channel).eq("external_id",externalId).maybeSingle();
  const row = checked(result,"Could not load this conversation.");
  if (!row) throw new SocialError("This conversation is not available.",404);
  return mapSocialContact(row as unknown as Row);
}

export async function socialPending(ctx: SocialContext, contact: SocialContact): Promise<SocialPending | null> {
  if (!contact.pendingId) return null;
  const result = await ctx.db.from("pending_replies").select(PENDING_COLUMNS).eq("model_id",ctx.model.id).eq("id",contact.pendingId).eq("channel",contact.channel).eq("status","awaiting").is("decision_command_id",null).maybeSingle();
  const row = checked(result,"Could not load reply suggestions.");
  if (!row) return null;
  if (row.conv_key !== contact.externalId && !(contact.channel === "instagram" && row.conv_key.split(":")[0] === contact.externalId)) return null;
  const suggestions = Array.isArray(row.suggestions) ? row.suggestions.filter((v: unknown): v is string => typeof v === "string") : [];
  const previews = contact.channel === "instagram" ? checked(await ctx.db.rpc("social_instagram_previews",{p_model:ctx.model.id,p_suggestions:suggestions}),"Could not prepare the exact reply preview.") as (string|null)[] : suggestions;
  return {id:row.id,channel:contact.channel,convKey:row.conv_key,suggestions,previews,incomingPreview:row.incoming_preview || "",hint:row.hint || "",createdAt:row.created_at,updatedAt:row.updated_at};
}

export function mapSocialCommand(row: Row, actionState?: string): SocialCommand {
  const result = row.result && typeof row.result === "object" ? row.result as Row : {};
  return {dismissedAt:str(row.ui_dismissed_at)||null,voicePreviewId:str(row.voice_preview_id)||undefined,mediaUuids:Array.isArray(row.media_uuids)?row.media_uuids as string[]:[],priceCents:Number(row.price_cents || 0),providerMessageId:str(result.provider_message_id)||null,id:str(row.id),operation:row.operation as SocialCommand["operation"],channel:row.channel as SocialChannel,externalId:str(row.external_id),text:str(row.text),status:row.status as SocialCommand["status"],deliveryState:actionState || str(result.delivery_state) || null,reason:str(row.reason),createdAt:str(row.created_at)};
}

export function ownerDraftForContact(commands:Row[],contact:SocialContact):SocialPending|null {
  const row=commands.find(c=>c.operation==="regenerate" && c.status==="done" && c.channel===contact.channel && c.external_id===contact.externalId && !c.pending_id
    && c.expected_source_id===contact.lastMessageId && c.account_scope===contact.accountScope && c.identity_id===contact.identityId
    && (c.identity_updated_at===contact.identityUpdatedAt || Date.parse(str(c.identity_updated_at))===Date.parse(contact.identityUpdatedAt || ""))
    && Date.parse(str(c.created_at))>Date.now()-30*60*1000 && Array.isArray((c.result as Row)?.owner_suggestions));
  if(!row || row.ui_dismissed_at)return null;
  const suggestions=((row.result as Row).owner_suggestions as unknown[]).filter((x):x is string=>typeof x==="string" && Boolean(x.trim()));
  return suggestions.length ? {id:str(row.id),channel:contact.channel,convKey:contact.externalId,suggestions,previews:suggestions,incomingPreview:"",hint:"",createdAt:str(row.created_at),updatedAt:str(row.finished_at)||str(row.created_at)} : null;
}

export async function loadSocialThread(modelId: string, key: string, before?: string): Promise<SocialThread> {
  const ctx = await socialContext(modelId);
  const contact = await socialContact(ctx,key);
  if (before && !/^\d{1,20}$/.test(before)) throw new SocialError("Invalid message cursor.");
  const channel = contact.channel;
  const table = channel === "telegram" ? "dm_messages" : channel === "fanvue" ? "fv_messages" : "ig_messages";
  const externalColumn = channel === "telegram" ? "tg_id" : channel === "fanvue" ? "fan_uuid" : "igsid";
  const timestamp = channel === "telegram" ? "created_at" : "occurred_at";
  const columns = `id,role,content,created_at,${channel === "telegram" ? "provider_message_id" : channel === "fanvue" ? "message_uuid" : "mid"}${channel !== "telegram" ? ",occurred_at" : ""}${channel === "instagram" ? ",metadata" : ""}`;
  let messagesQuery = ctx.db.from(table).select(columns).eq("model_id",modelId).eq(externalColumn,contact.externalId);
  if (before) {
    const cursorResult = await ctx.db.from(table).select(`id,${timestamp}`).eq("model_id",modelId).eq(externalColumn,contact.externalId).eq("id",before).maybeSingle();
    const cursor = checked(cursorResult,"Could not load earlier messages.") as Row | null;
    if (!cursor) throw new SocialError("This message cursor is no longer available.",409);
    if (cursor[timestamp]) {
      const value = new Date(str(cursor[timestamp])).toISOString();
      messagesQuery = messagesQuery.or(`${timestamp}.lt.${value},and(${timestamp}.eq.${value},id.lt.${before}),${timestamp}.is.null`);
    } else messagesQuery = messagesQuery.is(timestamp,null).lt("id",before);
  }
  const [messagesResult,pending,commandsResult,linkedResult,candidateResult] = await Promise.all([
    messagesQuery.order(timestamp,{ascending:false,nullsFirst:false}).order("id",{ascending:false}).limit(51),
    socialPending(ctx,contact),
    ctx.db.from("social_commands").select(COMMAND_COLUMNS).eq("model_id",modelId).eq("channel",channel).eq("external_id",contact.externalId).eq("account_scope",contact.accountScope).order("created_at",{ascending:false}).limit(12),
    contact.personId ? ctx.db.from("social_contact_summaries").select(CONTACT_COLUMNS).eq("model_id",modelId).eq("person_id",contact.personId).in("channel",ctx.channels) : Promise.resolve({data:[],error:null}),
    contact.candidateId ? ctx.db.from("social_contact_summaries").select(CONTACT_COLUMNS).eq("model_id",modelId).eq("identity_id",contact.candidateId).in("channel",ctx.channels).maybeSingle() : Promise.resolve({data:null,error:null}),
  ]);
  const rows = checked(messagesResult,"Could not load messages.") as unknown as Row[];
  const commands = checked(commandsResult,"Could not load delivery status.") as unknown as Row[];
  const actionIds = commands.map(c => str((c.result as Row)?.action_id)).filter(id => UUID.test(id));
  const actions = actionIds.length ? checked(await ctx.db.from("instagram_actions").select("id,state").eq("model_id",modelId).in("id",actionIds),"Could not load Instagram delivery status.") : [];
  const page = rows.slice(0,50);
  const media = await loadSocialMedia(ctx,contact,page.map(r => str(r.id)));
  return {contact,messages:page.map(r => ({...mapSocialMessage(channel,r),media:media[str(r.id)]?.media || [],content:media[str(r.id)]?.originalContent ?? str(r.content)})).reverse(),hasMore:rows.length>50,nextBefore:rows.length>50 ? str(page.at(-1)?.id) : null,pending,ownerDraft:ownerDraftForContact(commands,contact),
    commands:commands.map(c => mapSocialCommand(c,actions?.find(a => a.id === (c.result as Row)?.action_id)?.state)),
    linkedContacts:(checked(linkedResult,"Could not load linked accounts.") as unknown as Row[]).map(mapSocialContact),
    candidate:candidateResult.data ? mapSocialContact(checked(candidateResult,"Could not load a suggested account.") as unknown as Row) : null,loadedAt:new Date().toISOString()};
}

export function socialErrorMessage(error: unknown): string {
  return error instanceof SocialError ? error.message : "Could not complete this action. Refresh and try again.";
}

/** Notification targets resolve directly; a person need not be on the inbox page. */
export async function loadSocialSelection(modelId: string, contact: unknown): Promise<{thread: SocialThread | null; error: string | null}> {
  if (contact === undefined) return {thread: null, error: null};
  try {
    parseContactKey(contact);
    return {thread: await loadSocialThread(modelId, contact as string), error: null};
  } catch (error) {
    return {thread: null, error: socialErrorMessage(error)};
  }
}

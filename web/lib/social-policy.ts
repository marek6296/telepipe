import {mediaBundle} from "./fanvue-owner-policy.ts";
import type { SocialChannel, SocialCommandInput, SocialContact, SocialFilter, SocialMessage, SocialPending, SocialPerson } from "./social-types";

export class SocialError extends Error {
  status: number;
  constructor(message: string, status = 400) { super(message); this.status = status; }
}

export const SOCIAL_CHANNELS: SocialChannel[] = ["telegram", "instagram", "fanvue"];
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const str = (value: unknown) => typeof value === "string" ? value : value == null ? "" : String(value);
const nullable = (value: unknown) => str(value) || null;
const finite = (value: unknown) => Number.isFinite(Number(value)) ? Number(value) : 0;

export function authorizeSocialOwner(model: { id: string; account_id: string } | null, userId: string, role: string): SocialChannel[] {
  if (!model || !userId || model.account_id !== userId) throw new SocialError("This model is not available.", 404);
  return role === "superadmin" ? [...SOCIAL_CHANNELS] : ["telegram", "fanvue"];
}

export function parseContactKey(key: unknown): { channel: SocialChannel; externalId: string } {
  if (typeof key !== "string") throw new SocialError("Choose a conversation.");
  const [channel, externalId, extra] = key.split(":");
  if (extra !== undefined || !SOCIAL_CHANNELS.includes(channel as SocialChannel)
      || !externalId || (channel === "fanvue" ? !/^[a-zA-Z0-9_-]{1,128}$/.test(externalId) : !/^-?\d{1,40}$/.test(externalId)))
    throw new SocialError("Invalid conversation.");
  return {channel: channel as SocialChannel, externalId};
}

export function parseSocialQuery(params: URLSearchParams) {
  const channel = params.get("channel") || "all";
  const filter = params.get("filter") || "all";
  const offset = Number(params.get("offset") || 0);
  return {
    search: (params.get("search") || "").trim().slice(0, 100),
    channel: (SOCIAL_CHANNELS.includes(channel as SocialChannel) ? channel : "all") as SocialChannel | "all",
    filter: (["all", "needs_reply", "approvals", "manual"].includes(filter) ? filter : "all") as SocialFilter,
    offset: Number.isSafeInteger(offset) ? Math.max(0, Math.min(offset, 100_000)) : 0,
  };
}

export function validateSocialCommand(input: unknown, contact: SocialContact, pending: SocialPending | null): SocialCommandInput {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new SocialError("Invalid request.");
  const raw = input as Record<string, unknown>;
  if (typeof raw.requestId !== "string" || !UUID.test(raw.requestId)) throw new SocialError("Invalid request ID. Refresh and try again.");
  if (!["approve", "regenerate", "send_text", "send_media", "send_voice"].includes(str(raw.operation))) throw new SocialError("Unknown action.");
  if (raw.contactKey !== contact.key) throw new SocialError("The selected conversation changed. Refresh it.", 409);
  if (raw.expectedAccountScope !== contact.accountScope || raw.expectedSourceId !== contact.lastMessageId || raw.identityId !== contact.identityId
      || raw.identityUpdatedAt !== contact.identityUpdatedAt) throw new SocialError("This conversation changed. Review the latest messages first.", 409);
  const expected = raw.expectedSuggestions;
  const needsPending = raw.operation === "approve" || raw.pendingId != null;
  if (needsPending && (!pending || raw.pendingId !== pending.id || !Array.isArray(expected)
      || JSON.stringify(expected) !== JSON.stringify(pending.suggestions)))
    throw new SocialError("These suggestions are no longer current. Refresh the conversation.", 409);
  if (!needsPending && pending) throw new SocialError("A reply is waiting for approval. Refresh before replacing it.", 409);
  const text = raw.text === undefined ? "" : raw.text;
  const brief = raw.brief === undefined ? "" : raw.brief;
  if (typeof text !== "string" || typeof brief !== "string" || text.includes("\0") || brief.includes("\0"))
    throw new SocialError("Enter plain text.");
  if (!["regenerate","send_media"].includes(str(raw.operation)) && !text.trim()) throw new SocialError("Write a message first.");
  if (Array.from(text).length > 4000 || brief.length > 2000) throw new SocialError("This message is too long.");
  if (contact.channel === "instagram" && new TextEncoder().encode(text).length > 1000)
    throw new SocialError("Instagram messages must fit within 1,000 bytes. Shorten this reply.");
  if (raw.operation === "approve" && !(pending?.previews || pending?.suggestions || []).includes(text))
    throw new SocialError("Approve a displayed suggestion, or send your own text.", 409);
  let media: {mediaUuids:string[];priceCents:number}|undefined;
  if(raw.operation==="send_voice"){
    if(!["telegram","fanvue"].includes(contact.channel) || typeof raw.voicePreviewId!=="string" || !UUID.test(raw.voicePreviewId))throw new SocialError("Choose a ready voice preview.");
    if(!Number.isInteger(raw.priceCents ?? 0) || Number(raw.priceCents || 0)<0 || (Number(raw.priceCents)>0 && (contact.channel!=="fanvue" || Number(raw.priceCents)<300)))throw new SocialError("Choose Free or a Fanvue price of at least $3.00.");
  } else if(raw.operation==="send_media") {
    if(contact.channel!=="fanvue")throw new SocialError("Media bundles are only available on Fanvue.");
    try {media=mediaBundle(raw.mediaUuids,raw.priceCents);}catch(error){throw new SocialError(error instanceof Error?error.message:"Invalid media bundle.");}
  } else if((raw.mediaUuids as unknown[] | undefined)?.length || raw.priceCents)throw new SocialError("Invalid media action.");
  return {
    ...media,
    ...(raw.operation==="send_voice"?{voicePreviewId:raw.voicePreviewId as string,priceCents:Number(raw.priceCents || 0)}:{}),
    requestId: raw.requestId, operation: raw.operation as SocialCommandInput["operation"], contactKey: contact.key,
    ...(needsPending ? {pendingId: pending!.id, expectedSuggestions: [...pending!.suggestions]} : {}),
    expectedSourceId: contact.lastMessageId, expectedAccountScope: contact.accountScope, identityId: contact.identityId, identityUpdatedAt: contact.identityUpdatedAt,
    text, brief,
  };
}

export function mapSocialContact(row: Record<string, unknown>): SocialContact {
  const channel = str(row.channel) as SocialChannel;
  if (!SOCIAL_CHANNELS.includes(channel)) throw new SocialError("Unsupported channel data.", 503);
  const externalId = str(row.external_id);
  return {
    key: `${channel}:${externalId}`, channel, externalId, accountScope: str(row.account_scope) || "primary",
    identityId: nullable(row.identity_id), identityUpdatedAt: nullable(row.identity_updated_at), personId: nullable(row.person_id),
    identityStatus: str(row.identity_status) || "local", candidateId: nullable(row.candidate_id),
    displayName: str(row.display_name) || str(row.username) || externalId, username: str(row.username), avatarUrl: safeImageUrl(row.avatar_url),
    aiEnabled: row.ai_enabled !== false, humanTakeover: row.human_takeover === true, summary: str(row.summary), spentCents: finite(row.spent_cents),
    lastMessageId: nullable(row.last_message_id), lastMessageRole: ["user", "assistant"].includes(str(row.last_message_role)) ? row.last_message_role as "user" | "assistant" : null,
    lastMessageText: str(row.last_message_text), lastMessageAt: nullable(row.last_message_at), lastActivityAt: nullable(row.last_activity_at),
    needsReply: row.needs_reply === true || row.last_message_role === "user", pendingId: nullable(row.pending_id),
  };
}

function safeImageUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 4096) return null;
  try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password ? url.href : null; } catch { return null; }
}

export function mapSocialMessage(channel: SocialChannel, row: Record<string, unknown>): SocialMessage {
  const meta = row.metadata && typeof row.metadata === "object" ? row.metadata as Record<string, unknown> : {};
  const kind = str(meta.kind);
  return {
    id: str(row.id), providerId:nullable(channel === "telegram" ? row.provider_message_id : channel === "fanvue" ? row.message_uuid : row.mid), channel, role: row.role === "assistant" ? "assistant" : "user", content: str(row.content),
    occurredAt: nullable(channel === "telegram" ? row.created_at : row.occurred_at), recordedAt: str(row.created_at),
    attachment: kind && !["dm", "text"].includes(kind) ? {kind, url: safeImageUrl(meta.url)} : null,
  };
}

export function groupSocialPeople(contacts: SocialContact[]): SocialPerson[] {
  const groups = new Map<string, SocialContact[]>();
  for (const contact of contacts) {
    const id = contact.personId || contact.key;
    groups.set(id, [...(groups.get(id) || []), contact]);
  }
  return [...groups.entries()].map(([id, members]) => {
    members.sort((a,b) => (b.lastActivityAt || "").localeCompare(a.lastActivityAt || "") || a.key.localeCompare(b.key));
    const recent = members[0];
    return {id, name: recent.displayName, contacts: members, preview: recent.lastMessageText,
      lastActivityAt: recent.lastActivityAt, waitingCount: members.filter(c => c.pendingId).length};
  }).sort((a,b) => (b.lastActivityAt || "").localeCompare(a.lastActivityAt || "") || a.id.localeCompare(b.id));
}

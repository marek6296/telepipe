import type { SocialChannel, SocialContact, SocialCommand, SocialCommandInput, SocialMessage, SocialPerson, SocialThread } from "@/lib/social-types";

export function commandInProgress(command: SocialCommand): boolean {
  return ["queued", "working", "sending"].includes(command.status)
    || (command.operation !== "regenerate" && command.status === "done"
      && ["queued", "ready", "pending", "leased", "approval", "sending"].includes(command.deliveryState ?? ""));
}

export function commandLabel(command: SocialCommand): string {
  if (command.status === "done") {
    if (command.operation === "regenerate") return "Drafts updated";
    if (command.deliveryState === "sending") return "Sending";
    if (command.deliveryState === "sent" || command.deliveryState === "delivered") return "Sent";
    if (["queued", "ready", "pending", "leased", "approval"].includes(command.deliveryState ?? "")) return "Approved · queued";
    if (command.deliveryState === "uncertain") return "Delivery unconfirmed";
    if (["blocked", "cancelled", "expired", "skipped"].includes(command.deliveryState ?? "")) return "Not delivered";
    return "Completed";
  }
  return {
    queued: "Queued", working: "Preparing", sending: "Sending",
    blocked: "Blocked", stale: "Conversation changed", failed: "Failed", uncertain: "Delivery unconfirmed",
  }[command.status];
}

export function freezeIntent(input: SocialCommandInput): SocialCommandInput {
  return Object.freeze({ ...input, ...(input.mediaUuids ? {mediaUuids:Object.freeze([...input.mediaUuids]) as unknown as string[]}:{}), expectedSuggestions: input.expectedSuggestions ? [...input.expectedSuggestions] : undefined });
}

export function mergeMessages(previous: SocialMessage[], incoming: SocialMessage[]): SocialMessage[] {
  const messages = new Map(previous.map(message => [message.id, message]));
  for (const message of incoming) messages.set(message.id, message);
  return [...messages.values()].sort(compareMessages);
}

function compareMessages(a: SocialMessage, b: SocialMessage): number {
  if (a.occurredAt !== b.occurredAt) {
    if (!a.occurredAt) return -1;
    if (!b.occurredAt) return 1;
    const byTime = Date.parse(a.occurredAt) - Date.parse(b.occurredAt);
    if (byTime) return byTime;
  }
  // IDs are bigint in Postgres; Number would collapse neighbouring rows.
  const left = BigInt(a.id);
  const right = BigInt(b.id);
  return left < right ? -1 : left > right ? 1 : 0;
}

export function mergeThread(previous: SocialThread, next: SocialThread): SocialThread {
  if (previous.contact.key !== next.contact.key) return next;
  const olderLoaded = previous.messages[0] && next.messages[0] && compareMessages(previous.messages[0], next.messages[0]) < 0;
  return { ...next, messages: mergeMessages(previous.messages, next.messages),
    hasMore: olderLoaded ? previous.hasMore : next.hasMore,
    nextBefore: olderLoaded ? previous.nextBefore : next.nextBefore };
}

/** Each effect owns a scope, so a late action cannot restart an old reader. */
export function createReadScope(url: string) {
  let active = true;
  let sequence = 0;
  return { url, begin: () => ++sequence, accepts: (ticket: number) => active && ticket === sequence, dispose: () => { active = false; } };
}

export const CHANNEL_NAMES = { telegram: "Telegram", instagram: "Instagram", fanvue: "Fanvue" } as const;

export function sourceTime(iso: string | null): string {
  if (!iso) return "Time unknown";
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return "Time unknown";
  // Stable during SSR hydration; always label the timezone explicitly.
  return `${new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date)} UTC`;
}

/** All channels with an incoming turn still awaiting a reply or approval. */
export function waitingChannels(contacts:SocialContact[]):Set<SocialChannel> {
  return new Set(contacts.filter(contact=>contact.needsReply || Boolean(contact.pendingId)).map(contact=>contact.channel));
}

/** A platform filter changes the preview and destination, not identity links. */
export function personChannelView(person:SocialPerson, channel:SocialChannel|"all") {
  const contact=channel === "all" ? null : person.contacts.find(item=>item.channel===channel) ?? null;
  return {contact,name:contact ? contact.username ? `@${contact.username.replace(/^@/,"")}` : contact.displayName : person.name,
    preview:contact ? contact.lastMessageText : person.preview,
    lastActivityAt:contact ? contact.lastActivityAt : person.lastActivityAt,
    waitingCount:contact ? Number(Boolean(contact.pendingId)) : person.waitingCount};
}

export function waitingMessageCount(contacts:SocialContact[],channel:SocialChannel|"all"="all"):number {
  return contacts.filter(c=>channel==="all" || c.channel===channel).reduce((n,c)=>n+(c.waitingMessageCount || 0),0);
}

/** Pending outbox is UI-only; authoritative history receives a turn after delivery. */
export function outboxCommands(commands:SocialCommand[],messages:SocialMessage[]):SocialCommand[] {
  return commands.filter(c=>c.operation!=="regenerate" && c.text && !messages.some(m=>m.role==="assistant" && (
    c.providerMessageId && m.providerId ? c.providerMessageId===m.providerId
    : c.status==="done" && ["sent","delivered"].includes(c.deliveryState || "") && m.content===c.text && m.occurredAt && Date.parse(m.occurredAt)>=Date.parse(c.createdAt)-5000
  ))).sort((a,b)=>a.createdAt.localeCompare(b.createdAt));
}

export function commandExplanation(command:SocialCommand):string {
  if(command.status==="queued" && command.reason.startsWith("waiting_"))return "Waiting for Instagram’s delivery limits. This reply will send automatically; you can leave this chat.";
  const reasons:Record<string,string>={
    generation_empty:"No new preview was created. Refresh the conversation and try Say this again. Nothing was sent.",
    voice_preview_expired:"This voice preview expired. Generate a new voice reply.",
    voice_preview_changed:"This voice belongs to an older reply. Generate a fresh preview.",
    voice_environment_changed:"Her current location changed. Generate a new voice preview for the current setting.",
    voice_preview_unavailable:"The voice preview is unavailable. Generate it again before sending.",
    voice_upload_failed:"The voice could not be uploaded to Fanvue. Nothing was sent.",
    voice_processing_failed:"Fanvue could not process the voice note. Nothing was sent.",
    voice_still_processing:"Fanvue is still processing the voice. Wait a moment before trying this preview again.",
    media_not_ready:"Some selected Fanvue media is not ready. Wait for processing in Vault, then try again.",
    media_unavailable:"Could not verify the selected Fanvue media. Refresh Vault before trying again.",
    invalid_media:"Choose a valid Fanvue media bundle and a Free or paid unlock price.",
    fanvue_rejected_400:"Fanvue rejected the message. Check the selected media and unlock price.",
    fanvue_rejected_403:"Fanvue did not allow this message. Check the account connection and media permissions.",
    provider_pause:"Instagram is temporarily paused after a connection error. This reply was not sent. Try again after the connection recovers.",
    window_expired:"Instagram's reply window has expired. Wait for a new message from this person.",
    instagram_disconnected:"Reconnect Instagram before replying.",
    stale_context:"The conversation changed before sending. Review the latest messages and choose a fresh reply.",
    draft_changed:"The suggestions changed. Review the current suggestions.",
    global_pause:"Replies are paused. Resume the agent before sending.",
    dm_limit:"Instagram's message limit has been reached. Try later.",
    history_unavailable:"Conversation history could not be refreshed. Try again once the connection recovers.",
  };
  return reasons[command.reason] || "";
}

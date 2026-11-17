/** Safe DTOs shared by the Social sites UI and its authenticated server API. */
export type SocialChannel = "telegram" | "instagram" | "fanvue";
export type SocialMode = "off" | "semi" | "auto";
export type SocialFilter = "all" | "needs_reply" | "approvals" | "manual";

export type SocialChannelState = {
  channel: SocialChannel;
  connected: boolean;
  available: boolean;
  handle: string;
  mode: SocialMode;
  connectHref: string;
  settingsHref: string;
  syncStatus: string;
  lastSyncAt: string | null;
  notice: string | null;
};

export type SocialContact = {
  key: string;
  channel: SocialChannel;
  externalId: string;
  accountScope: string;
  identityId: string | null;
  identityUpdatedAt: string | null;
  personId: string | null;
  identityStatus: string;
  candidateId: string | null;
  displayName: string;
  username: string;
  avatarUrl: string | null;
  aiEnabled: boolean;
  humanTakeover: boolean;
  summary: string;
  spentCents: number;
  lastMessageId: string | null;
  lastMessageRole: "user" | "assistant" | null;
  lastMessageText: string;
  lastMessageAt: string | null;
  lastActivityAt: string | null;
  needsReply: boolean;
  waitingMessageCount?:number;
  pendingId: string | null;
};

export type SocialPerson = {
  id: string;
  name: string;
  contacts: SocialContact[];
  preview: string;
  lastActivityAt: string | null;
  waitingCount: number;
};

export type SocialSnapshot = {
  modelId: string;
  modelName: string;
  channels: SocialChannelState[];
  people: SocialPerson[];
  total: number;
  offset: number;
  pageSize: number;
  loadedAt: string;
  agent: { running: boolean; status: string; paused: boolean; timezone: string; schedule: string };
};

export type SocialMedia = {
  id: string;
  kind: "audio" | "video" | "image" | "file";
  playbackUrl: string | null;
  mimeType: string | null;
  transcript: string | null;
  description: string | null;
  status: "pending" | "processing" | "ready" | "unavailable" | "failed";
  error: string | null;
  durationSeconds: number | null;
};

export type SocialMessage = {
  id: string;
  channel: SocialChannel;
  role: "user" | "assistant";
  content: string;
  occurredAt: string | null;
  recordedAt: string;
  providerId?:string|null;
  attachment: { kind: string; url: string | null } | null;
  media?: SocialMedia[];
};

export type SocialPending = {
  id: string;
  channel: SocialChannel;
  convKey: string;
  suggestions: string[];
  previews?: (string | null)[];
  incomingPreview: string;
  hint: string;
  createdAt: string;
  updatedAt: string;
};

export type SocialCommand = {
  voicePreviewId?:string;
  mediaUuids?:string[];
  priceCents?:number;
  providerMessageId?:string|null;
  id: string;
  operation: "approve" | "regenerate" | "send_text" | "send_media" | "send_voice";
  channel: SocialChannel;
  externalId: string;
  text: string;
  status: "queued" | "working" | "sending" | "done" | "blocked" | "stale" | "failed" | "uncertain";
  deliveryState: string | null;
  reason: string;
  createdAt: string;
};

export type SocialThread = {
  contact: SocialContact;
  messages: SocialMessage[];
  hasMore: boolean;
  nextBefore: string | null;
  pending: SocialPending | null;
  commands: SocialCommand[];
  linkedContacts: SocialContact[];
  candidate: SocialContact | null;
  loadedAt: string;
};

export type SocialCommandInput = {
  voicePreviewId?:string;
  mediaUuids?:string[];
  priceCents?:number;
  requestId: string;
  operation: "approve" | "regenerate" | "send_text" | "send_media" | "send_voice";
  contactKey: string;
  pendingId?: string;
  expectedSuggestions?: string[];
  expectedSourceId: string | null;
  expectedAccountScope: string;
  identityId: string | null;
  identityUpdatedAt: string | null;
  text?: string;
  brief?: string;
};

export type SocialResult = { error?: string; message?: string; command?: SocialCommand; retryable?: boolean };

export type SocialBrief = {summary:string;generatedAt:string|null;coverage:string;truncated:boolean;generating:boolean;accounts:{channel:SocialChannel;name:string}[]};
export type SocialBriefResult = {brief?:SocialBrief;error?:string};

export type FanvueMediaItem={uuid:string;name:string;kind:string;status:string;thumb:string};
export type FanvueMediaJobResult={job?:{id:string;status:string;output:Record<string,unknown>;error:string};error?:string};

export type SocialVoicePreview={id:string;status:'queued'|'working'|'ready'|'failed';text:string;spoken:string;ambience:string;playbackUrl:string|null;error:string;expiresAt:string};
export type SocialVoiceRequest={id:string;contactKey:string;input?:SocialCommandInput;regenerate?:boolean};
export type SocialVoiceResult={preview?:SocialVoicePreview;error?:string};

import type { SocialChannel, SocialCommandInput, SocialMode, SocialResult, SocialBriefResult, FanvueMediaJobResult, SocialVoiceRequest, SocialVoiceResult } from "@/lib/social-types";

export interface SocialTransport {
  dismissSocialCommand:(modelId:string,contactKey:string,commandId:string)=>Promise<SocialResult>;
  socialVoicePreview(modelId:string,request:SocialVoiceRequest):Promise<SocialVoiceResult>;
  fanvueOwnerMedia(modelId:string,scope:string,input:unknown):Promise<FanvueMediaJobResult>;
  getSocialPersonBrief(modelId:string,contactKey:string,refresh?:boolean):Promise<SocialBriefResult>;
  read<T>(url: string, signal?: AbortSignal): Promise<T>;
  submitSocialCommand(modelId: string, input: SocialCommandInput): Promise<SocialResult>;
  setSocialMode(modelId: string, channel: SocialChannel, mode: SocialMode): Promise<SocialResult>;
  setSocialTakeover(modelId: string, contactKey: string, takeover: boolean): Promise<SocialResult>;
  linkSocialContacts(modelId: string, firstKey: string, secondKey: string): Promise<SocialResult>;
  unlinkSocialContact(modelId: string, contactKey: string): Promise<SocialResult>;
  skipSocialPending(modelId: string, pendingId: string, expectedSuggestions: string[]): Promise<SocialResult>;
}
export const SESSION_EXPIRED = "Your session ended. Close this window and reopen Social sites from your Telegram bot.";
class TransportError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

export function createMiniTransport({token, onExpired, fetcher = fetch}: {token?: string; onExpired: () => void; fetcher?: typeof fetch}): SocialTransport & {refresh: () => Promise<{expiresAt: string}>} {
  let expired = false;
  async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
    if (expired) throw new TransportError(SESSION_EXPIRED,401);
    // Never attach the session to provider URLs, redirects, or normalized traversal.
    if (!/^\/api\/(?:models\/[\w-]+\/social(?:\/thread)?(?:\?|$)|mini\/(?:actions|refresh)$)/.test(url)
      || url.includes("\\") || url.split("?")[0].includes("..")) throw new Error("Invalid Social API path.");
    const headers = new Headers(options.headers);
    headers.set("X-Telepipe-Mini","1");
    if (token) headers.set("Authorization",`Bearer ${token}`);
    const response = await fetcher(url,{...options,headers,credentials:"include",cache:"no-store",redirect:"error"});
    if (response.status === 401) { expired = true; onExpired(); throw new TransportError(SESSION_EXPIRED,401); }
    const body = await response.json();
    if (!response.ok) throw new TransportError(typeof body.error === "string" ? body.error : "Could not complete the request. Try again.",response.status);
    return body as T;
  }
  async function action(modelId: string, action: string, args: object): Promise<SocialResult> {
    try { return await request<SocialResult>("/api/mini/actions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({modelId,action,...args})}); }
    catch (error) { return {error:error instanceof Error ? error.message : "The response was interrupted. Retry the same request.", retryable:!(error instanceof TransportError) || error.status >= 500}; }
  }
  return {
    socialVoicePreview:async(modelId,input)=>{try{return await request<SocialVoiceResult>("/api/mini/actions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({modelId,action:"voice_preview",input})});}catch(error){return {error:error instanceof Error?error.message:"Could not load voice preview."};}},
    fanvueOwnerMedia:async(modelId,scope,input)=>{
      try{return await request<FanvueMediaJobResult>("/api/mini/actions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({modelId,action:"fanvue_media",scope,input})});}
      catch(error){return {error:error instanceof Error?error.message:"Could not complete media request."};}
    },
    getSocialPersonBrief:async(modelId,contactKey,refresh=false)=>{
      try{return await request<SocialBriefResult>("/api/mini/actions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({modelId,action:"brief",contactKey,refresh})});}
      catch(error){return {error:error instanceof Error?error.message:"Could not load the summary. Try again."};}
    },
    read:<T>(url: string, signal?: AbortSignal) => request<T>(url,{signal}),
    refresh:() => request<{expiresAt:string}>("/api/mini/refresh",{method:"POST"}),
    dismissSocialCommand:(modelId,contactKey,commandId)=>action(modelId,"dismiss",{contactKey,commandId}),
    submitSocialCommand:(modelId,input) => action(modelId,"command",{input}),
    setSocialMode:(modelId,channel,mode) => action(modelId,"mode",{channel,mode}),
    setSocialTakeover:(modelId,contactKey,takeover) => action(modelId,"takeover",{contactKey,takeover}),
    linkSocialContacts:(modelId,firstKey,secondKey) => action(modelId,"link",{firstKey,secondKey}),
    unlinkSocialContact:(modelId,contactKey) => action(modelId,"unlink",{contactKey}),
    skipSocialPending:(modelId,pendingId,expectedSuggestions) => action(modelId,"skip",{pendingId,expectedSuggestions}),
  };
}

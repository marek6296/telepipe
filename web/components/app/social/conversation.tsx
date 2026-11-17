"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, RefreshCw, Send, SkipForward, Sparkles } from "lucide-react";
import { useSocialTransport } from "./transport";
import type { SocialChannelState, SocialCommandInput, SocialContact, SocialMessage, SocialThread } from "@/lib/social-types";
import { cn } from "@/lib/utils";
import { PersonPanel } from "./person-panel";
import { MessageMedia } from "./message-media";
import { CHANNEL_NAMES, commandInProgress, commandLabel, commandExplanation, freezeIntent, mergeMessages, mergeThread, outboxCommands, sourceTime } from "./state";
import { useSocialResource } from "./use-resource";
import type { ComposerDraft, UpdateDraft } from "./workspace";

export function Conversation({ modelId, contact, channelState, draft, updateDraft, selectContact, refreshInbox, initialThread }: {
  modelId: string; contact: SocialContact; channelState?: SocialChannelState; draft: ComposerDraft; initialThread?: SocialThread;
  updateDraft: UpdateDraft; selectContact: (contact: SocialContact) => void; refreshInbox: () => void;
}) {
  const { transport, mini } = useSocialTransport();
  const { skipSocialPending, submitSocialCommand } = transport;
  const params = new URLSearchParams({ channel: contact.channel, externalId: contact.externalId });
  const url = `/api/models/${modelId}/social/thread?${params}`;
  const resource = useSocialResource<SocialThread>(url, initialThread, mergeThread, threadPollInterval);
  const thread = resource.data;
  const current = thread?.contact ?? contact;
  const [olderLoading, setOlderLoading] = useState(false);
  const [olderError, setOlderError] = useState("");
  const [skipLoading, setSkipLoading] = useState(false);
  const olderController = useRef<AbortController | null>(null);
  const actionBusy = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastSeenMessage = useRef<string | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const regeneratingRevision = useRef<string | null>(null);
  const previewRevision = thread?.pending ? `${thread.pending.id}:${thread.pending.updatedAt}` : null;
  const localIntent = draft.activity?.input;
  const commandRows = thread?.commands || [];
  const optimistic = localIntent && (draft.submitting || Boolean(draft.retry)) && localIntent.operation!=="regenerate" && !commandRows.some(c=>c.id===localIntent.requestId)
    ? [{id:localIntent.requestId,operation:localIntent.operation,channel:current.channel,externalId:current.externalId,text:localIntent.text || "",status:draft.error ? draft.retry ? "uncertain" as const : "failed" as const : "queued" as const,deliveryState:null,reason:"",createdAt:new Date().toISOString()}] : [];
  const outbox = outboxCommands([...commandRows,...optimistic],thread?.messages || []);
  const lastId = outbox.at(-1)?.id || thread?.messages.at(-1)?.id;
  const waitingForCommand = thread?.commands.some(commandInProgress) ?? false;
  const activeCommand = thread?.commands.find(item => item.id === draft.activity?.command?.id)
    ?? draft.activity?.command ?? thread?.commands.find(commandInProgress);
  const progressBusy = draft.submitting || Boolean(activeCommand && commandInProgress(activeCommand));
  const progressError = Boolean(draft.error || (activeCommand && (["failed", "uncertain", "blocked", "stale"].includes(activeCommand.status)
    || ["uncertain", "blocked", "cancelled", "expired", "skipped"].includes(activeCommand.deliveryState ?? ""))));
  const progressText = draft.submitting ? "Submitting…" : draft.error || (activeCommand ? [commandLabel(activeCommand),commandExplanation(activeCommand)].filter(Boolean).join(" · ") : draft.notice);
  const canSend = Boolean(thread && channelState?.available && channelState.connected && !resource.error);
  const blocked = !canSend || waitingForCommand || draft.submitting || skipLoading || Boolean(draft.retry);

  useEffect(() => () => { olderController.current?.abort(); }, []);
  useEffect(() => {
    if (!lastId) return;
    const scroll = scrollRef.current;
    if (!scroll) return;
    if (!lastSeenMessage.current || scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 130) scroll.scrollTop = scroll.scrollHeight;
    lastSeenMessage.current = lastId;
  }, [lastId]);

  useEffect(() => {
    if (regeneratingRevision.current && previewRevision && regeneratingRevision.current !== previewRevision) {
      regeneratingRevision.current = null;
      previewRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [previewRevision]);

  function changeDraft(change: Partial<ComposerDraft>) {
    updateDraft(contact.key, previous => ({ ...previous, ...change }));
  }
  function refreshAll() { void resource.refresh(); refreshInbox(); }

  async function loadOlder() {
    if (!thread?.nextBefore || olderLoading) return;
    const controller = new AbortController();
    olderController.current?.abort(); olderController.current = controller;
    setOlderLoading(true); setOlderError("");
    const top = scrollRef.current?.scrollTop ?? 0;
    const height = scrollRef.current?.scrollHeight ?? 0;
    try {
      const body = await transport.read<SocialThread>(`${url}&before=${encodeURIComponent(thread.nextBefore)}`, controller.signal);
      if (controller.signal.aborted || body.contact?.key !== contact.key) return;
      const older = body as SocialThread;
      resource.update(previous => ({ ...previous, messages: mergeMessages(older.messages, previous.messages), hasMore: older.hasMore, nextBefore: older.nextBefore }));
      requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = top + scrollRef.current.scrollHeight - height; });
    } catch (error) { if (!controller.signal.aborted) setOlderError(error instanceof Error ? error.message : "Could not load older messages."); }
    finally { if (!controller.signal.aborted) setOlderLoading(false); }
  }

  async function submit(input: SocialCommandInput) {
    if (actionBusy.current || draft.submitting) return;
    actionBusy.current = true;
    changeDraft({ submitting: true, error: "", notice: "", retry: input, activity: {input} });
    try {
      const result = await submitSocialCommand(modelId, input);
      if (result.error) {
        changeDraft({ error: result.error, retry: result.retryable ? input : null, activity: {input} });
        if (!result.retryable) { regeneratingRevision.current = null; refreshAll(); }
      } else {
        updateDraft(contact.key, previous => ({ ...previous, retry: null, activity: {input, command: result.command}, notice: result.command ? commandLabel(result.command) : result.message || "Request accepted.",
          text: input.operation === "send_text" && previous.text.trim() === input.text ? "" : previous.text }));
        if (result.command) resource.update(previous => ({ ...previous, commands: [result.command!, ...previous.commands.filter(command => command.id !== result.command!.id)] }));
        refreshAll();
      }
    } catch {
      changeDraft({ error: "The response was interrupted. Check the request using Retry; it keeps the same request ID and will not create a second send." });
    } finally { actionBusy.current = false; changeDraft({ submitting: false }); }
  }

  function command(operation: SocialCommandInput["operation"], text?: string, brief?: string) {
    if (!thread || blocked) return;
    const pending = thread.pending;
    if (operation !== "send_text" && !pending) return;
    const input = freezeIntent({ requestId: crypto.randomUUID(), operation, contactKey: thread.contact.key, expectedAccountScope: thread.contact.accountScope,
      expectedSourceId: thread.contact.lastMessageId, identityId: thread.contact.identityId,
      identityUpdatedAt: thread.contact.identityUpdatedAt,
      // A custom answer also replaces the exact draft currently visible, if any.
      ...(pending ? { pendingId: pending.id, expectedSuggestions: pending.suggestions } : {}),
      ...(text !== undefined ? { text } : {}), ...(brief !== undefined ? { brief } : {}) });
    if (operation === "regenerate") regeneratingRevision.current = previewRevision;
    void submit(input);
  }

  async function skip() {
    if (!thread?.pending || actionBusy.current || blocked) return;
    actionBusy.current = true; setSkipLoading(true); changeDraft({ error: "", notice: "", activity: null });
    const pending = thread.pending;
    try {
      const result = await skipSocialPending(modelId, pending.id, [...pending.suggestions]);
      if (result.error) changeDraft({ error: result.error });
      else { changeDraft({ notice: "Draft skipped." }); refreshAll(); }
    } catch { changeDraft({ error: "Could not skip this draft. Refresh and try again." }); }
    finally { actionBusy.current = false; setSkipLoading(false); }
  }

  return <div className="social-conversation grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_200px]">
    <section className="social-conversation-card app-card min-w-0 overflow-hidden" aria-label={`${CHANNEL_NAMES[contact.channel]} conversation with ${current.displayName}`}>
      <div className="social-chat-header border-b border-[var(--app-border)] px-4 py-3.5">
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="truncate text-[15px] font-medium">{current.displayName || current.username || current.externalId}</h2><p className="mt-0.5 text-[11px] text-[var(--app-text-3)]">{CHANNEL_NAMES[current.channel]}{current.username ? ` · @${current.username.replace(/^@/, "")}` : ""}{current.humanTakeover ? " · You are replying" : ""}</p></div><button type="button" disabled={resource.loading} onClick={() => void resource.refresh()} aria-label="Refresh conversation" className="app-btn app-btn-quiet h-8 w-8"><RefreshCw className={cn("h-3.5 w-3.5", resource.loading && "animate-spin")} /></button></div>
        {thread && thread.linkedContacts.length > 1 && <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Choose sending account">{thread.linkedContacts.map(linked => <button type="button" key={linked.key} onClick={() => selectContact(linked)} aria-pressed={linked.key === current.key} className={cn("rounded-md border px-2.5 py-1.5 text-[10.5px]", linked.key === current.key ? "border-[var(--app-text-3)] bg-[var(--app-surface-hover)] text-[var(--app-text)]" : "border-[var(--app-border)] text-[var(--app-text-3)]")}>{CHANNEL_NAMES[linked.channel]}</button>)}</div>}
      </div>
      {resource.error && <div role="alert" className="border-b border-[var(--app-border)] px-4 py-3 text-[11px] text-[#fca5a5]">{resource.error} {thread ? "Replies are disabled until the conversation refreshes." : ""}<button type="button" onClick={() => void resource.refresh()} className="ml-2 underline">Retry</button></div>}
      <div className="social-conversation-body" ref={mini ? scrollRef : undefined}>
      <div ref={mini ? undefined : scrollRef} className="social-history h-[400px] overflow-y-auto overscroll-contain px-4 py-4 sm:h-[450px]" aria-label="Message history" aria-busy={!thread && resource.loading}>
        {!thread ? <div role="status" className="flex h-full items-center justify-center gap-2 text-[12px] text-[var(--app-text-3)]">{resource.loading ? <><Loader2 className="h-4 w-4 animate-spin" />Loading conversation</> : "Conversation could not be loaded."}</div> : <>
          {thread.hasMore && <div className="mb-4 text-center"><button type="button" onClick={() => void loadOlder()} disabled={olderLoading} className="app-btn app-btn-quiet mx-auto min-h-8 px-3 text-[11px]">{olderLoading && <Loader2 className="h-3 w-3 animate-spin" />}Load older messages</button></div>}
          {olderError && <p role="alert" className="mb-3 text-center text-[11px] text-[#fca5a5]">{olderError}</p>}
          {thread.messages.length === 0 ? <div className="flex h-full items-center justify-center text-center text-[12px] text-[var(--app-text-3)]">No imported messages for this account yet.</div> : <div className="space-y-3">{thread.messages.map(message => <Message key={message.id} message={message} refreshPlayback={async mediaId => (await resource.refresh())?.messages.find(row => row.id === message.id)?.media?.find(item => item.id === mediaId)?.playbackUrl} />)}</div>}
        </>}
      {thread && outbox.length>0 && <div className="mt-3 space-y-3">{outbox.map(item=><div key={item.id} className="flex justify-end"><div className="max-w-[88%] rounded-xl rounded-br-sm bg-[#252525] px-3 py-2.5 text-[12px] leading-5"><p className="whitespace-pre-wrap break-words">{item.text}</p><p className="mt-1 flex items-center justify-end gap-1.5 text-[10px] text-[var(--app-text-3)]">{commandInProgress(item) && <Loader2 className="h-3 w-3 animate-spin" />}{optimistic.some(c=>c.id===item.id) ? draft.error ? "Not confirmed · check request" : "Submitting…" : commandLabel(item)}</p>{["failed","blocked","stale","uncertain"].includes(item.status) && <p role="alert" className="mt-1 text-[10px] text-[#fca5a5]">{item.status==="uncertain" ? "Delivery unconfirmed. Check the channel before retrying." : commandExplanation(item) || "Not sent. Review this conversation before trying again."}</p>}</div></div>)}</div>}
      </div>
      {thread?.pending && !commandRows.some(c=>c.operation!=="regenerate" && commandInProgress(c)) && <div ref={previewRef} className="social-suggestions border-t border-[var(--app-border)] bg-white/[0.015] p-4">
        <div className="mb-3 flex items-center justify-between gap-2"><h3 className="flex items-center gap-1.5 text-[12px] font-medium"><Sparkles className="h-3.5 w-3.5" />Suggested replies</h3>{!mini && <span className="text-[10px] text-[var(--app-text-4)]">Review, then approve</span>}</div>
        {!mini && <p className="mb-3 text-[10.5px] leading-5 text-[var(--app-text-3)]">These are the exact messages she will send. Nothing is sent until you approve.</p>}
        {!mini && thread.pending.incomingPreview && <p className="mb-3 line-clamp-2 border-l border-[var(--app-border-strong)] pl-2.5 text-[11px] leading-5 text-[var(--app-text-3)]">{thread.pending.incomingPreview}</p>}
        <div className="space-y-2">{thread.pending.suggestions.map((rawSuggestion, index) => { const suggestion = thread.pending!.previews ? thread.pending!.previews[index] : rawSuggestion; const selected = draft.activity?.input.operation === "approve" && draft.activity.input.pendingId === thread.pending!.id && draft.activity.input.text === suggestion && !progressError; return <div key={`${thread.pending!.id}-${index}-${rawSuggestion}`} className="social-suggestion rounded-lg border border-[var(--app-border)] bg-[var(--app-bg)] p-3"><p className="whitespace-pre-wrap break-words text-[12px] leading-5">{suggestion || "This suggestion cannot be sent as text. Regenerate a new reply."}</p><div className="social-suggestion-action mt-2 flex justify-end"><button aria-label={mini ? (selected && progressText ? `Reply ${index + 1}: ${progressText}` : `Send reply ${index + 1}`) : undefined} title={mini ? `Send reply ${index + 1}` : undefined} type="button" onClick={() => command("approve", suggestion || "")} disabled={blocked || !suggestion} className="app-btn app-btn-ghost min-h-8 px-2.5 text-[10.5px]">{selected && progressBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : mini ? <Send className="h-4 w-4" /> : <Check className="h-3 w-3" />}{!mini && (selected && progressText ? progressText : `Approve reply ${index + 1}`)}</button></div></div>; })}</div>
        {thread.pending.suggestions.length === 0 && <p className="text-[11px] text-[var(--app-text-3)]">No text suggestions yet. Regenerate a draft or write your own reply.</p>}
        {!mini && thread.pending.hint && <p className="mt-2 text-[10.5px] text-[var(--app-text-4)]">{thread.pending.hint}</p>}
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2"><button type="button" disabled={blocked} onClick={() => command("regenerate")} className="inline-flex min-h-8 items-center gap-1.5 text-[11px] text-[var(--app-text-2)] disabled:opacity-40"><RefreshCw className="h-3 w-3" />Regenerate</button><button type="button" disabled={blocked} onClick={() => void skip()} className="ml-auto inline-flex min-h-8 items-center gap-1 text-[11px] text-[var(--app-text-3)] disabled:opacity-40">{skipLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <SkipForward className="h-3 w-3" />}Skip</button></div>
        <details className="social-say-this" open={mini ? undefined : true}>
          {mini && <summary className="flex min-h-10 cursor-pointer items-center gap-2 text-[12px] font-medium"><Sparkles className="h-3.5 w-3.5" />Say this<span className="ml-auto text-[var(--app-text-3)]">＋</span></summary>}
        <form onSubmit={event => { event.preventDefault(); if (draft.brief.trim()) command("regenerate", undefined, draft.brief.trim()); }} className="mt-3 rounded-lg border border-[var(--app-border-strong)] bg-[var(--app-bg)] p-3">
          <label htmlFor={`say-this-${current.channel}`} className={mini ? "sr-only" : "flex items-center gap-1.5 text-[12px] font-medium"}><Sparkles className="h-3.5 w-3.5" />Say this</label>
          {!mini && <p className="mt-1.5 text-[10.5px] leading-5 text-[var(--app-text-3)]">Write what you mean. She will phrase it in her own voice, using this conversation. You review the new previews above before approving.</p>}
          <textarea id={`say-this-${current.channel}`} value={draft.brief} onChange={event => changeDraft({ brief: event.target.value })} maxLength={2000} rows={2} placeholder={mini ? "What should she say?" : "Tell him I enjoyed the walk and ask how his weekend went…"} className="app-input mt-2 resize-y text-[12px]! leading-5!" />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">{!mini && <span className="text-[10px] text-[var(--app-text-4)]">Creates previews only.</span>}<button type="submit" disabled={blocked || !draft.brief.trim()} className="app-btn app-btn-ghost min-h-9 px-3 text-[11px]">{draft.submitting || waitingForCommand ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}Preview in her voice</button></div>
        </form>
        </details>
      </div>}
      {!mini && thread && thread.commands.length > 0 && <div className="border-t border-[var(--app-border)] px-4 py-3"><h3 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[var(--app-text-4)]">Recent requests</h3><ul className="space-y-2">{thread.commands.slice(0, 5).map(item => <li key={item.id} className="text-[10.5px]"><div className="flex justify-between gap-2"><span className={cn(["failed", "uncertain", "blocked", "stale"].includes(item.status) ? "text-[#fca5a5]" : "text-[var(--app-text-2)]")}>{commandLabel(item)}</span><span className="text-[var(--app-text-4)]">{sourceTime(item.createdAt)}</span></div>{item.text && <p className="mt-0.5 line-clamp-2 break-words text-[var(--app-text-3)]">{item.text}</p>}{item.reason && <p className="mt-0.5 break-words text-[var(--app-text-4)]">{item.reason}</p>}{(item.status === "uncertain" || item.deliveryState === "uncertain") && <p className="mt-1 text-[#fca5a5]">Check the channel before sending again. This request will not be resent automatically.</p>}</li>)}</ul></div>}
      {mini && thread && <details className="border-t border-[var(--app-border)] p-4"><summary className="cursor-pointer text-[12px] font-medium">Person &amp; conversation controls</summary><div className="mt-3"><PersonPanel key={current.key} modelId={modelId} thread={thread} selectContact={selectContact} refresh={refreshAll} /></div></details>}
      </div>
      {(progressText || draft.retry) && <div className="shrink-0 border-t border-[var(--app-border-strong)] bg-[var(--app-surface)] px-4 py-3">
        <p role={progressError ? "alert" : "status"} aria-live={progressError ? "assertive" : "polite"} aria-atomic="true" className={cn("flex items-center gap-2 text-[12px] font-medium", progressError ? "text-[#fca5a5]" : "text-[var(--app-text)]")}>
          {progressBusy ? <Loader2 aria-hidden="true" className="h-4 w-4 shrink-0 animate-spin" /> : !progressError && <Check aria-hidden="true" className="h-4 w-4 shrink-0" />}{progressText}
        </p>
        {progressBusy && <p className="mt-1 text-[10.5px] text-[var(--app-text-3)]">Please wait — your request is in progress.</p>}
        {draft.retry && !draft.submitting && <button type="button" onClick={() => void submit(draft.retry!)} className="app-btn app-btn-ghost mt-2 min-h-8 px-3 text-[11px]">Retry the same request</button>}
      </div>}
      <form onSubmit={event => { event.preventDefault(); if (draft.text.trim()) command("send_text", draft.text.trim()); }} className="social-exact-composer border-t border-[var(--app-border)] p-4">
        <label htmlFor={`reply-${current.channel}`} className="mb-2 flex items-center justify-between gap-2 text-[11px] font-medium"><span>Write my own · {CHANNEL_NAMES[current.channel]}</span><span className="truncate font-normal text-[var(--app-text-4)]">To {current.displayName || current.username || current.externalId}</span></label>
        <textarea id={`reply-${current.channel}`} value={draft.text} onChange={event => changeDraft({ text: event.target.value })} onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); if (draft.text.trim()) command("send_text", draft.text.trim()); } }} rows={mini ? 1 : 3} maxLength={12000} placeholder={mini ? "Message…" : "Write the exact message to send…"} className="app-input resize-y text-[12px]! leading-5!" />

        <div className="social-composer-actions mt-3 flex items-center justify-between gap-3"><p className="max-w-[65%] text-[10px] leading-4 text-[var(--app-text-4)]">{!channelState?.connected ? "Connect this channel before replying." : waitingForCommand ? "A request is in progress. Its delivery status appears above." : channelState.mode === "auto" ? "Your exact text is sent unchanged and takes over this conversation. AI pauses here until you resume it." : "Your text is sent unchanged. Ctrl / ⌘ + Enter to send."}</p><button type="submit" disabled={blocked || !draft.text.trim()} className="app-btn app-btn-primary min-h-9 shrink-0 px-3 text-[11px]">{progressBusy && draft.activity?.input.operation === "send_text" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}{progressBusy && draft.activity?.input.operation === "send_text" ? progressText : mini ? "Send" : "Send exact text"}</button></div>
      </form>
    </section>
    {!mini && thread && <PersonPanel key={current.key} modelId={modelId} thread={thread} selectContact={selectContact} refresh={refreshAll} />}
  </div>;
}

function Message({ message, refreshPlayback }: { message: SocialMessage; refreshPlayback:(mediaId:string)=>Promise<string|null|undefined> }) {
  const own = message.role === "assistant";
  return <div className={cn("flex", own ? "justify-end" : "justify-start")}><div className={cn("min-w-0 max-w-[88%] rounded-xl px-3 py-2.5 text-[12px] leading-5", own ? "social-message-own rounded-br-sm bg-[#252525] text-[var(--app-text)]" : "social-message-inbound rounded-bl-sm border border-[var(--app-border)] bg-[#131313] text-[var(--app-text-2)]")}>
    <MessageMedia message={message} refreshPlayback={refreshPlayback} />
    {message.content && <p className="whitespace-pre-wrap break-words">{message.content}</p>}
    <p className="mt-1 text-right text-[9px] leading-4 text-[var(--app-text-4)]" title={message.occurredAt ? `${message.occurredAt} · original message time` : "Original message time is unknown. Import time is not shown as message time."}>{sourceTime(message.occurredAt)}</p>
  </div></div>;
}

function threadPollInterval(thread:SocialThread|undefined) { return thread?.commands.some(commandInProgress) ? 1000 : 5000; }
